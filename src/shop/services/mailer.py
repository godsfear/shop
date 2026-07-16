"""Почта: подтверждение почты кодом ДО создания учётки (анти-спам, AWS-стиль).

Заявка на регистрацию целиком живёт в Redis (signup:{email}, TTL): код +
данные формы с уже захешированным паролем. В БД до подтверждения — ничего;
не подтвердил — заявка испарилась. Письмо — через outbox (надёжно, той же
транзакцией, что и постановка заявки).

Провайдер по приоритету: Resend (HTTP API, если задан RESEND_API_KEY) ->
SMTP-релей (SMTP_HOST) -> лог (dev, ничего не настроено).
"""
import json
import secrets
import smtplib
import urllib.error
import urllib.request
from asyncio import to_thread
from email.message import EmailMessage

from sqlalchemy.ext.asyncio import AsyncSession

from ..cache import get_cache
from ..logger import logger
from ..outbox import emit, outbox_handler
from ..settings import settings

TOPIC_EMAIL = 'notify.email'
_NS = 'signup'


async def request_signup(session: AsyncSession, email: str, pending: dict) -> None:
    """Заявка на регистрацию: код + данные в Redis, письмо в очередь.
    Повторная заявка на тот же адрес перезаписывает прежнюю (новый код)."""
    code = f'{secrets.randbelow(1_000_000):06d}'
    await get_cache().set(f'{_NS}:{email.lower()}',
                          json.dumps({'code': code, 'pending': pending}),
                          settings.confirm_ttl_s)
    emit(session, TOPIC_EMAIL, {
        'to': email,
        'subject': 'Код подтверждения регистрации',
        'body': (f'Ваш код подтверждения: {code}\nОн действует 24 часа. '
                 'Если вы не регистрировались — просто проигнорируйте это письмо.'),
    })


async def pop_signup(email: str, code: str) -> dict | None:
    """Сверка кода: совпал — заявка изымается (одноразово) и возвращается."""
    key = f'{_NS}:{email.lower()}'
    raw = await get_cache().get(key)
    if raw is None:
        return None
    obj = json.loads(raw)
    if obj.get('code') != code.strip():
        return None
    await get_cache().delete(key)
    return obj['pending']


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
