"""Health check router."""
from __future__ import annotations

from fastapi import APIRouter

router = APIRouter(tags=["health"])


@router.get("/health", summary="Health check")
async def health():
    return {"status": "ok", "service": "agentic-ReAct"}

