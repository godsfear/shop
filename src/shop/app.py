from fastapi import FastAPI
from starlette.middleware.base import BaseHTTPMiddleware
from shop.middleware import middleware_proc

from shop.api import router

app = FastAPI()
#app.add_middleware(BaseHTTPMiddleware, dispatch=middleware_proc)
app.include_router(router)
