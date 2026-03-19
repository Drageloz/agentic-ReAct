"""
Agent Router — POST /chat  (SSE streaming)
           — GET  /conversations/{conversation_id}
           — GET  /conversations?user_id=...
"""
from __future__ import annotations

import logging
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse

from app.api.v1.schemas.chat_request import ChatRequest, SSEEvent
from app.application.use_cases.get_history import GetConversationHistoryUseCase
from app.application.use_cases.run_agent import RunAgentUseCase
from app.dependencies import get_run_agent_use_case, get_history_use_case

logger = logging.getLogger(__name__)
router = APIRouter(tags=["agent"])


@router.post(
    "/chat",
    summary="Send a query to the ReAct agent (SSE streaming)",
    response_description="Server-Sent Events stream of ReAct steps",
)
async def chat(
    request: ChatRequest,
    use_case: RunAgentUseCase = Depends(get_run_agent_use_case),
) -> StreamingResponse:
    """
    Streams the ReAct agent's reasoning as SSE events.

    Event types emitted:
    - `thought`       — agent reasoning text
    - `action`        — tool invocation request
    - `observation`   — tool result
    - `final_answer`  — the conclusive response
    - `done`          — stream complete (includes conversation_id)
    - `error`         — an error occurred
    """

    async def event_generator():
        try:
            async for event in use_case.execute(
                user_id=request.user_id,
                query=request.query,
                conversation_id=request.conversation_id,
                user_context=request.user_context,
                rag_id=request.rag_id,
            ):
                sse = SSEEvent(event=event["event"], data=event["data"])
                yield sse.to_sse_string()
        except Exception as exc:
            logger.exception("Agent execution error")
            error_event = SSEEvent(event="error", data={"detail": str(exc)})
            yield error_event.to_sse_string()

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",  # Disable nginx buffering
        },
    )