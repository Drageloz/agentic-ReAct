"""
Security Middleware — validates every incoming request before it reaches the routes.

Protections:
  1. API Key validation (header X-API-Key)
  2. Prompt injection detection (common injection patterns)
  3. Sensitive data request detection (salary, password, SSN, etc.)
  4. Maximum prompt length enforcement
"""
from __future__ import annotations

import json
import logging
import re
from typing import Callable

from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import JSONResponse

logger = logging.getLogger(__name__)

# ── Injection patterns ────────────────────────────────────────────────────────
_INJECTION_PATTERNS: list[re.Pattern] = [
    re.compile(r"ignore\s+(all\s+)?(previous|prior|above)\s+instructions?", re.I),
    re.compile(r"you\s+are\s+now\s+(?:a|an|the)\s+", re.I),
    re.compile(r"disregard\s+(your|all|any)\s+", re.I),
    re.compile(r"forget\s+everything", re.I),
    re.compile(r"act\s+as\s+(?:if\s+you\s+are|a|an)\s+", re.I),
    re.compile(r"jailbreak", re.I),
    re.compile(r"<\s*script\s*>", re.I),          # XSS
    re.compile(r"--\s*;?\s*DROP\s+TABLE", re.I),  # SQL injection
    re.compile(r"UNION\s+SELECT", re.I),
    re.compile(r"\bexec\s*\(", re.I),
    re.compile(r"system\s*prompt", re.I),
    re.compile(r"reveal\s+(your\s+)?(instructions?|prompt|system)", re.I),
]

# ── Sensitive data keywords ───────────────────────────────────────────────────
_SENSITIVE_KEYWORDS: list[re.Pattern] = [
    re.compile(r"\bsalar(?:y|ies|io)\b", re.I),
    re.compile(r"\bpassword\b", re.I),
    re.compile(r"\bcontraseña\b", re.I),
    re.compile(r"\bssn\b|\bsocial\s+security\b", re.I),
    re.compile(r"\bcredit\s+card\b|\btarjeta\s+de\s+cr[eé]dito\b", re.I),
    re.compile(r"\bbank\s+account\b|\bcuenta\s+bancaria\b", re.I),
    re.compile(r"\bpin\s+code\b|\bpin\b", re.I),
    re.compile(r"\btax\s+id\b|\bnif\b|\bdni\b", re.I),
]

_MAX_PROMPT_LENGTH = 4096


class SecurityMiddleware(BaseHTTPMiddleware):
    def __init__(self, app, valid_api_keys: list[str], api_key_header: str = "X-API-Key") -> None:
        super().__init__(app)
        self._valid_keys = set(valid_api_keys)
        self._header_name = api_key_header

    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        # ── Skip for health check and docs ─────────────────────────────────
        if request.url.path in ("/health", "/docs", "/openapi.json", "/redoc"):
            return await call_next(request)

        # ── 1. API Key validation ──────────────────────────────────────────
        api_key = request.headers.get(self._header_name)
        if not api_key or api_key not in self._valid_keys:
            logger.warning("Rejected request — invalid API key from %s", request.client)
            return JSONResponse(
                status_code=401,
                content={"detail": "Invalid or missing API key."},
            )

        # ── 2. Inspect body for POST requests ─────────────────────────────
        if request.method == "POST":
            try:
                body_bytes = await request.body()
                body_text = body_bytes.decode("utf-8", errors="replace")
                body_json = json.loads(body_text) if body_text else {}
            except Exception:
                body_json = {}
                body_text = ""

            query: str = body_json.get("query", "") or ""

            # 2a. Length check
            if len(query) > _MAX_PROMPT_LENGTH:
                return JSONResponse(
                    status_code=422,
                    content={"detail": f"Query exceeds maximum length of {_MAX_PROMPT_LENGTH} characters."},
                )

            # 2b. Injection detection
            for pattern in _INJECTION_PATTERNS:
                if pattern.search(query):
                    logger.warning("Prompt injection detected from user %s: %r", body_json.get("user_id"), query[:80])
                    return JSONResponse(
                        status_code=400,
                        content={"detail": "Query contains disallowed content (possible prompt injection)."},
                    )

            # 2c. Sensitive data detection
            for pattern in _SENSITIVE_KEYWORDS:
                if pattern.search(query):
                    logger.warning("Sensitive data request from user %s: %r", body_json.get("user_id"), query[:80])
                    return JSONResponse(
                        status_code=403,
                        content={"detail": "Access to sensitive personal data is not permitted through this interface."},
                    )

            # Re-attach the body so downstream handlers can read it
            async def receive():
                return {"type": "http.request", "body": body_bytes, "more_body": False}

            request = Request(request.scope, receive)

        return await call_next(request)

