"""HTTP 请求日志中间件。"""

from __future__ import annotations

import time
from collections.abc import Callable

from fastapi import Request, Response
from loguru import logger
from starlette.middleware.base import BaseHTTPMiddleware


class RequestLoggingMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        start = time.perf_counter()
        response = await call_next(request)
        elapsed_ms = (time.perf_counter() - start) * 1000

        if request.url.path.endswith("/health"):
            return response

        logger.bind(
            method=request.method,
            path=request.url.path,
            status=response.status_code,
            elapsed_ms=round(elapsed_ms, 2),
            client=request.client.host if request.client else "-",
        ).info("HTTP {} {} -> {} ({:.2f}ms)", request.method, request.url.path, response.status_code, elapsed_ms)

        return response
