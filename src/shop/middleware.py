import time

from fastapi import Request, Response

from shop.logger import logger
from shop.services.auth import AuthService


async def middleware_proc(request: Request, call_next):
    """Access-лог без содержимого: тела запросов/ответов НЕ читаются и НЕ логируются
    (пароли, ПДн, мед. данные; см. память проекта — псевдонимизация). Размеры берутся
    из заголовков, тело ответа не буферизуется — стриминг остаётся стримингом.
    Query string не логируется тоже: в ней бывают токены и идентификаторы.
    """
    start = time.perf_counter()
    response: Response = await call_next(request)
    # безопасные заголовки; HSTS — на TLS-терминаторе (nginx/traefik), не здесь
    response.headers.setdefault('X-Content-Type-Options', 'nosniff')
    response.headers.setdefault('X-Frame-Options', 'DENY')
    response.headers.setdefault('Referrer-Policy', 'no-referrer')
    # скользящая сессия: успешный запрос активного пользователя продлевает
    # токен (фронт подхватывает X-Refresh-Token); отказы токен не продлевают
    auth = request.headers.get('authorization', '')
    if response.status_code < 400 and auth.startswith('Bearer '):
        fresh = AuthService.refresh_if_stale(auth[7:])
        if fresh:
            response.headers['X-Refresh-Token'] = fresh
    logger.info({
        "method": request.method,
        "path": request.url.path,
        "status": response.status_code,
        "process_time": round(time.perf_counter() - start, 6),
        "client": request.client.host if request.client else None,
        "request_bytes": request.headers.get("content-length"),
        "response_bytes": response.headers.get("content-length"),
    })
    return response
