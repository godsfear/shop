"""Фоновые процессы отдельным сервисом: python -m shop.worker.

Два режима (settings.event_bus):
- false (по умолчанию): in-DB outbox_worker разбирает очередь напрямую;
- true: relay перекачивает outbox -> RabbitMQ, консумеры читают из очередей
  (см. eventbus.py). Масштаб ИИ-обработки — репликами этого процесса.

Для многопроцессного прода: web-реплики с RUN_WORKERS=false, воркеры — этим
сервисом. Импорт сервисов ниже регистрирует @outbox_handler (нужно и релею,
и консумерам, и in-DB воркеру)."""
import asyncio

from .logger import logger
from .settings import settings
from .services import evaluate as _evaluate            # noqa: F401 — @outbox_handler
from .services import mailer as _mailer                # noqa: F401 — @outbox_handler
from .services import extract as _extract              # noqa: F401 — @outbox_handler
from .services import notifications as _notifications  # noqa: F401 — @outbox_handler
from .services import nutrition as _nutrition          # noqa: F401 — @outbox_handler
from .services import sleep as _sleep                  # noqa: F401 — @outbox_handler
from .services.bridge import pseudonym_pool_topper
from .services.consent import consent_sweeper


def background_coros() -> list:
    """Корутины фоновых задач под текущий режим (используют и worker, и lifespan api)."""
    coros = [consent_sweeper(), pseudonym_pool_topper()]
    if settings.event_bus:
        from .eventbus import consume_loop, relay_loop
        return [relay_loop(), consume_loop(), *coros]
    from .outbox import outbox_worker
    return [outbox_worker(), *coros]


async def main() -> None:
    logger.info('shop.worker: режим %s', 'шина RabbitMQ' if settings.event_bus else 'in-DB outbox')
    await asyncio.gather(*background_coros())


if __name__ == '__main__':
    asyncio.run(main())
