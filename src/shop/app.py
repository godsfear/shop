import asyncio
from contextlib import asynccontextmanager, suppress

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import text
from starlette.middleware.base import BaseHTTPMiddleware

from shop.database import db_helper
from shop.middleware import middleware_proc
from shop.api import router
from shop.settings import settings
from shop.worker import background_coros


@asynccontextmanager
async def lifespan(_: FastAPI):
    # RUN_WORKERS=false на репликах — фон отдельным процессом (shop.worker).
    # background_coros регистрирует @outbox_handler и выбирает режим (шина/in-DB).
    tasks = [asyncio.create_task(c) for c in background_coros()] \
        if settings.run_workers else []
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
