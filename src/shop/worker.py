"""Фоновые воркеры отдельным процессом: python -m shop.worker.

Для многопроцессного прода: web-реплики поднимаются с RUN_WORKERS=false
(иначе каждая реплика дублирует циклы), воркеры — ровно один такой процесс.
Очередь конкурентно-безопасна (FOR UPDATE SKIP LOCKED), так что дубль
воркера не ломает корректность — только жжёт соединения.
"""
import asyncio

from .logger import logger
from .outbox import outbox_worker
from .services import evaluate as _evaluate            # noqa: F401 — @outbox_handler
from .services import extract as _extract              # noqa: F401 — @outbox_handler
from .services import notifications as _notifications  # noqa: F401 — @outbox_handler
from .services.bridge import pseudonym_pool_topper
from .services.consent import consent_sweeper


async def main() -> None:
    logger.info('shop.worker: outbox + consent sweeper + pseudonym pool')
    await asyncio.gather(outbox_worker(), consent_sweeper(), pseudonym_pool_topper())


if __name__ == '__main__':
    asyncio.run(main())
