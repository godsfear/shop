import asyncio
from contextlib import asynccontextmanager, suppress

from fastapi import FastAPI
from starlette.middleware.base import BaseHTTPMiddleware

from shop.middleware import middleware_proc
from shop.api import router
from shop.outbox import outbox_worker


@asynccontextmanager
async def lifespan(_: FastAPI):
    # обработчики outbox зарегистрированы импортом сервисов (shop.api -> services)
    worker = asyncio.create_task(outbox_worker())
    yield
    worker.cancel()
    with suppress(asyncio.CancelledError):
        await worker


app = FastAPI(lifespan=lifespan)
app.add_middleware(BaseHTTPMiddleware, dispatch=middleware_proc)
app.include_router(router)
