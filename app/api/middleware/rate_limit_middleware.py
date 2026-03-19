"""
Rate Limit Middleware — sliding window in-memory rate limiter.
Keyed by API key (from header) or client IP as fallback.
"""
from __future__ import annotations

import logging
import time
from collections import defaultdict, deque
from typing import Callable

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse, Response

logger = logging.getLogger(__name__)


class RateLimitMiddleware(BaseHTTPMiddleware):
    def __init__(
        self,
        app,
        max_requests: int = 20,
        window_seconds: int = 60,
        api_key_header: str = "X-API-Key",
    ) -> None:
        super().__init__(app)
        self._max_requests = max_requests
        self._window = window_seconds
        self._header = api_key_header
        # { client_key: deque([timestamp, ...]) }
        self._windows: dict[str, deque] = defaultdict(deque)

    def _get_client_key(self, request: Request) -> str:
        key = request.headers.get(self._header)
        if key:
            return f"apikey:{key}"
        client = request.client
        return f"ip:{client.host if client else 'unknown'}"

    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        if request.url.path in ("/health", "/docs", "/openapi.json", "/redoc"):
            return await call_next(request)

        client_key = self._get_client_key(request)
        now = time.monotonic()
        window_start = now - self._window
        q = self._windows[client_key]

        # Evict old timestamps
        while q and q[0] < window_start:
            q.popleft()

        if len(q) >= self._max_requests:
            retry_after = int(self._window - (now - q[0])) + 1
            logger.warning("Rate limit exceeded for %s", client_key)
            return JSONResponse(
                status_code=429,
                content={
                    "detail": f"Rate limit exceeded. Try again in {retry_after} seconds."
                },
                headers={"Retry-After": str(retry_after)},
            )

        q.append(now)
        response = await call_next(request)
        remaining = self._max_requests - len(q)
        response.headers["X-RateLimit-Limit"] = str(self._max_requests)
        response.headers["X-RateLimit-Remaining"] = str(remaining)
        response.headers["X-RateLimit-Window"] = str(self._window)
        return response

