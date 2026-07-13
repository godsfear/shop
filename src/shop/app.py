import asyncio
from contextlib import asynccontextmanager, suppress

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import text
from starlette.middleware.base import BaseHTTPMiddleware

from shop.database import db_helper
from shop.middleware import middleware_proc
from shop.api import router
from shop.outbox import outbox_worker
from shop.services import evaluate as _evaluate  # noqa: F401 — @outbox_handler('episode.evaluate')
from shop.services import mailer as _mailer      # noqa: F401 — @outbox_handler('notify.email')
from shop.services import extract as _extract  # noqa: F401 — @outbox_handler('data.extract')
from shop.services.bridge import pseudonym_pool_topper
from shop.services.consent import consent_sweeper
from shop.settings import settings


@asynccontextmanager
async def lifespan(_: FastAPI):
    # обработчики outbox зарегистрированы импортом сервисов (shop.api -> services);
    # RUN_WORKERS=false на репликах — воркеры отдельным процессом (shop.worker)
    tasks = [asyncio.create_task(outbox_worker()),
             asyncio.create_task(consent_sweeper()),
             asyncio.create_task(pseudonym_pool_topper())] if settings.run_workers else []
    yield
    for task in tasks:
        task.cancel()
    for task in tasks:
        with suppress(asyncio.CancelledError):
            await task


app = FastAPI(lifespan=lifespan)
app.add_middleware(BaseHTTPMiddleware, dispatch=middleware_proc)
if settings.cors_origins:  # без CORS_ORIGINS в .env браузерные кросс-домены закрыты
    app.add_middleware(CORSMiddleware, allow_origins=settings.cors_origins,
                       allow_credentials=True, allow_methods=['*'], allow_headers=['*'])
app.include_router(router)


@app.get('/health')
async def health() -> dict:
    """Liveness/readiness: БД отвечает — ok; иначе 500 (балансировщик выведет из ротации)."""
    async with db_helper.session_factory() as session:
        await session.execute(text('SELECT 1'))
    return {'status': 'ok'}
