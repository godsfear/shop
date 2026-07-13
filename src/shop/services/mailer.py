"""Почта: подтверждение регистрации кодом. Отправка — через outbox (надёжно,
той же транзакцией, что и регистрация); SMTP не задан — код в лог (dev).

Код живёт в Redis (emailconfirm:{user_id}, TTL) и генерится в момент запроса
(signup/resend), консумер только доставляет письмо.
"""
import secrets
import smtplib
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


def _send_smtp(to: str, subject: str, body: str) -> None:
    msg = EmailMessage()
    msg['From'], msg['To'], msg['Subject'] = settings.mail_from, to, subject
    msg.set_content(body)
    with smtplib.SMTP(settings.smtp_host, settings.smtp_port, timeout=15) as smtp:
        smtp.starttls()
        if settings.smtp_user:
            smtp.login(settings.smtp_user, settings.smtp_password)
        smtp.send_message(msg)


@outbox_handler(TOPIC_EMAIL)
async def _deliver(session: AsyncSession, payload: dict) -> None:
    if not settings.smtp_host:
        # dev: письмо не уходит — код виден в логе сервера
        logger.info('почта (dev, SMTP не настроен) для %s: %s | %s',
                    payload['to'], payload['subject'], payload['body'].replace('\n', ' '))
        return
    await to_thread(_send_smtp, payload['to'], payload['subject'], payload['body'])
