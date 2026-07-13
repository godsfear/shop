"""Почта: подтверждение регистрации кодом. Отправка — через outbox (надёжно,
той же транзакцией, что и регистрация).

Провайдер по приоритету: Resend (HTTP API, если задан RESEND_API_KEY) ->
SMTP-релей (SMTP_HOST) -> лог (dev, ничего не настроено). Код живёт в Redis
(emailconfirm:{user_id}, TTL) и генерится при запросе (signup/resend),
консумер только доставляет письмо.
"""
import json
import secrets
import smtplib
import urllib.error
import urllib.request
import uuid
from asyncio import to_thread
from email.message import EmailMessage

from sqlalchemy.ext.asyncio import AsyncSession

from ..cache import get_cache
from ..logger import logger
from ..outbox import emit, outbox_handler
from ..settings import settings

TOPIC_EMAIL = 'notify.email'
_NS = 'emailconfirm'


async def request_confirm(session: AsyncSession, user_id: uuid.UUID, email: str) -> None:
    """Генерит код, кладёт в Redis и ставит письмо в очередь (в транзакции вызывающего)."""
    code = f'{secrets.randbelow(1_000_000):06d}'
    await get_cache().set(f'{_NS}:{user_id}', code, settings.confirm_ttl_s)
    emit(session, TOPIC_EMAIL, {
        'to': email,
        'subject': 'Код подтверждения',
        'body': f'Ваш код подтверждения: {code}\nОн действует 24 часа.',
    })


async def check_confirm(user_id: uuid.UUID, code: str) -> bool:
    saved = await get_cache().get(f'{_NS}:{user_id}')
    if saved is None or saved != code.strip():
        return False
    await get_cache().delete(f'{_NS}:{user_id}')  # код одноразовый
    return True


def _send_resend(to: str, subject: str, body: str) -> None:
    """Отправка через Resend HTTP API (dependency-free: тот же вызов, что и SDK).
    from обязан быть с проверенного домена; sandbox onboarding@resend.dev шлёт
    только на почту владельца аккаунта — прод требует свой домен в Resend."""
    req = urllib.request.Request(
        'https://api.resend.com/emails',
        data=json.dumps({'from': settings.mail_from, 'to': [to],
                         'subject': subject, 'text': body}).encode(),
        headers={'Authorization': f'Bearer {settings.resend_api_key}',
                 'Content-Type': 'application/json',
                 # без явного UA Cloudflare перед Resend режет Python-urllib (err 1010)
                 'User-Agent': 'shop-mailer/1.0'},
        method='POST')
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            resp.read()
    except urllib.error.HTTPError as e:
        detail = e.read().decode('utf-8', 'replace')[:300]
        raise RuntimeError(f'Resend {e.code}: {detail}') from None


def _send_smtp(to: str, subject: str, body: str) -> None:
    msg = EmailMessage()
    msg['From'], msg['To'], msg['Subject'] = settings.mail_from, to, subject
    msg.set_content(body)
    with smtplib.SMTP(settings.smtp_host, settings.smtp_port, timeout=15) as smtp:
        if settings.smtp_starttls:            # ловушка без TLS (Mailpit) — выключить
            smtp.starttls()
        if settings.smtp_user:
            smtp.login(settings.smtp_user, settings.smtp_password)
        smtp.send_message(msg)


@outbox_handler(TOPIC_EMAIL)
async def _deliver(session: AsyncSession, payload: dict) -> None:
    to, subject, body = payload['to'], payload['subject'], payload['body']
    if settings.resend_api_key:
        await to_thread(_send_resend, to, subject, body)
        return
    if settings.smtp_host:
        await to_thread(_send_smtp, to, subject, body)
        return
    # dev: провайдер не настроен — код виден в логе сервера
    logger.info('почта (dev, провайдер не настроен) для %s: %s | %s',
                to, subject, body.replace('\n', ' '))
