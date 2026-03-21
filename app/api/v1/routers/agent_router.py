from __future__ import annotations

import logging
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import JSONResponse, StreamingResponse

from app.api.v1.schemas.chat_request import ChatRequest, SSEEvent
from app.application.use_cases.get_history import GetConversationHistoryUseCase
from app.application.use_cases.run_agent import RunAgentUseCase, AgentError, LLMError, ERPError
from app.dependencies import get_run_agent_use_case, get_history_use_case

logger = logging.getLogger(__name__)
router = APIRouter(tags=["agent"])


@router.post(
    "/chat",
    summary="Send a query to the ReAct agent (SSE streaming)",
    response_description="Server-Sent Events stream of ReAct steps",
    responses={
        200: {"description": "SSE stream of ReAct steps"},
        503: {"description": "LLM service unavailable"},
        502: {"description": "ERP/database unreachable"},
        500: {"description": "Unexpected internal error"},
    },
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
    - `error`         — a structured error occurred (JSON with code + detail)
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

        except LLMError as exc:
            logger.error("LLM service error: %s", exc)
            error_event = SSEEvent(
                event="error",
                data={
                    "code": "LLM_UNAVAILABLE",
                    "detail": (
                        "The AI model is temporarily unavailable. "
                        "Please try again in a few moments."
                    ),
                    "retry": True,
                },
            )
            yield error_event.to_sse_string()

        except ERPError as exc:
            logger.error("ERP/database error: %s", exc)
            error_event = SSEEvent(
                event="error",
                data={
                    "code": "ERP_UNAVAILABLE",
                    "detail": (
                        "Could not retrieve data from the ERP system. "
                        "The database may be unreachable."
                    ),
                    "retry": False,
                },
            )
            yield error_event.to_sse_string()

        except AgentError as exc:
            logger.error("Agent logic error: %s", exc)
            error_event = SSEEvent(
                event="error",
                data={
                    "code": "AGENT_ERROR",
                    "detail": str(exc),
                    "retry": False,
                },
            )
            yield error_event.to_sse_string()

        except Exception as exc:
            logger.exception("Unexpected agent execution error")
            error_event = SSEEvent(
                event="error",
                data={
                    "code": "INTERNAL_ERROR",
                    "detail": "An unexpected error occurred. Our team has been notified.",
                    "retry": True,
                },
            )
            yield error_event.to_sse_string()

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",  # Disable nginx buffering
        },
    )


@router.get(
    "/conversations/{conversation_id}",
    summary="Get conversation history by ID",
)
async def get_conversation(
    conversation_id: UUID,
    use_case: GetConversationHistoryUseCase = Depends(get_history_use_case),
):
    try:
        result = await use_case.get_by_id(conversation_id)
        if result is None:
            raise HTTPException(status_code=404, detail="Conversation not found")
        return result
    except HTTPException:
        raise
    except Exception as exc:
        logger.exception("Error fetching conversation %s", conversation_id)
        raise HTTPException(status_code=503, detail="Could not retrieve conversation history") from exc


@router.get(
    "/conversations",
    summary="List conversations for a user",
)
async def list_conversations(
    user_id: str,
    use_case: GetConversationHistoryUseCase = Depends(get_history_use_case),
):
    try:
        return await use_case.get_by_user(user_id)
    except Exception as exc:
        logger.exception("Error listing conversations for user %s", user_id)
        raise HTTPException(status_code=503, detail="Could not list conversation history") from exc

