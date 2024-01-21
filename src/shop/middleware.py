from fastapi import Request, Response
import time
from shop.logger import logger


async def middleware_proc(request: Request, call_next):
    process_time: float = time.time()
    response: Response = await call_next(request)
    request_body: bytes = await request.body()
    response_body: bytes = b""
    async for chunk in response.body_iterator:
        response_body += chunk
    process_time = time.time() - process_time

    log_dict = {
        "url": request.url.path,
        "method": request.method,
        "process_time": process_time,
        "request": request_body.decode(),
        "response": response_body.decode()
    }
    logger.info(log_dict)
    return Response(
        content=response_body,
        status_code=response.status_code,
        headers=dict(response.headers),
        media_type=response.media_type
    )
