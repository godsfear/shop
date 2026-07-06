import time

from fastapi import Request, Response

from shop.logger import logger


async def middleware_proc(request: Request, call_next):
    """Access-лог без содержимого: тела запросов/ответов НЕ читаются и НЕ логируются
    (пароли, ПДн, мед. данные; см. память проекта — псевдонимизация). Размеры берутся
    из заголовков, тело ответа не буферизуется — стриминг остаётся стримингом.
    Query string не логируется тоже: в ней бывают токены и идентификаторы.
    """
    start = time.perf_counter()
    response: Response = await call_next(request)
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
