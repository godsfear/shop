import asyncio
from contextlib import asynccontextmanager, suppress

from fastapi import FastAPI
from starlette.middleware.base import BaseHTTPMiddleware

from shop.middleware import middleware_proc
from shop.api import router
from shop.outbox import outbox_worker
from shop.services import extract as _extract  # noqa: F401 — @outbox_handler('data.extract')
from shop.services.bridge import pseudonym_pool_topper
from shop.services.consent import consent_sweeper


@asynccontextmanager
async def lifespan(_: FastAPI):
    # обработчики outbox зарегистрированы импортом сервисов (shop.api -> services)
    tasks = [asyncio.create_task(outbox_worker()),
             asyncio.create_task(consent_sweeper()),
             asyncio.create_task(pseudonym_pool_topper())]
    yield
    for task in tasks:
        task.cancel()
    for task in tasks:
        with suppress(asyncio.CancelledError):
            await task


app = FastAPI(lifespan=lifespan)
app.add_middleware(BaseHTTPMiddleware, dispatch=middleware_proc)
app.include_router(router)
