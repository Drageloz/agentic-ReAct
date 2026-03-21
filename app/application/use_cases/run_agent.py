"""
RunAgentUseCase — entry point for processing a chat request.

Orchestrates:
  1. Load or create Conversation
  2. Add user message
  3. Run ReactOrchestrator (streaming)
  4. Persist updated Conversation
  5. Yield SSE-ready dicts

Exceptions:
  LLMError  — raised when the LLM provider is unreachable / returns an error
  ERPError  — raised when the ERP/DB is unreachable
  AgentError — raised for other agent-logic failures
"""
from __future__ import annotations

import logging
from typing import Any, AsyncIterator
from uuid import UUID, uuid4

from app.application.services.react_orchestrator import ReactOrchestrator
from app.domain.entities.agent import AgentState, StepType
from app.domain.entities.conversation import Conversation, Message, MessageRole
from app.domain.ports.conversation_repository_port import ConversationRepositoryPort

logger = logging.getLogger(__name__)


# ── Domain-level error hierarchy ──────────────────────────────────────────────

class AgentError(Exception):
    """Base class for agent errors."""


class LLMError(AgentError):
    """Raised when the LLM provider fails (network, rate-limit, auth)."""


class ERPError(AgentError):
    """Raised when the ERP / database is unreachable or returns an error."""


class RunAgentUseCase:
    def __init__(
        self,
        orchestrator: ReactOrchestrator,
        conversation_repo: ConversationRepositoryPort,
        max_iterations: int = 10,
    ) -> None:
        self._orchestrator = orchestrator
        self._repo = conversation_repo
        self._max_iterations = max_iterations

    async def execute(
        self,
        user_id: str,
        query: str,
        conversation_id: UUID | None = None,
        user_context: dict[str, Any] | None = None,
        rag_id: str | None = None,
    ) -> AsyncIterator[dict[str, Any]]:
        """
        Async generator that yields SSE-compatible event dicts.
        Each dict has at minimum: {"event": str, "data": any}
        """
        # ── Load or create conversation ────────────────────────────────────
        if conversation_id:
            conversation = await self._repo.find_by_id(conversation_id)
        else:
            conversation = None

        if conversation is None:
            conversation = Conversation(
                conversation_id=conversation_id or uuid4(),
                user_id=user_id,
                user_context=user_context,
                rag_id=rag_id,
            )

        conversation.add_message(Message(role=MessageRole.USER, content=query))

        # ── Build initial agent state ─────────────────────────────────────
        state = AgentState(
            session_id=uuid4(),
            user_id=user_id,
            original_query=query,
            max_iterations=self._max_iterations,
        )

        # ── Stream ReAct steps ────────────────────────────────────────────
        final_answer_text = ""

        try:
            async for step in self._orchestrator.run(state):
                event_data = step.to_dict()
                yield {"event": step.step_type.value, "data": event_data}

                if step.step_type == StepType.FINAL_ANSWER:
                    final_answer_text = step.content

        except Exception as exc:
            exc_str = str(exc).lower()
            exc_type = type(exc).__name__

            # Classify the error by inspecting its type/message
            if any(kw in exc_str for kw in (
                "openai", "anthropic", "api key", "rate limit", "quota",
                "authentication", "authenticationerror", "ratelimiterror",
                "apierror", "timeout", "connectionerror",
            )) or any(kw in exc_type.lower() for kw in (
                "openai", "anthropic", "ratelimit", "apierror",
            )):
                raise LLMError(f"LLM provider error: {exc}") from exc

            if any(kw in exc_str for kw in (
                "mysql", "operationalerror", "programmingerror",
                "can't connect", "connection refused", "getaddrinfo",
                "table", "doesn't exist", "no module named 'greenlet'",
                "sqlalchemy",
            )) or any(kw in exc_type.lower() for kw in (
                "operationalerror", "programmingerror", "sqlerror",
            )):
                raise ERPError(f"ERP/database error: {exc}") from exc

            raise AgentError(f"Agent execution failed: {exc}") from exc

        # ── Persist conversation ──────────────────────────────────────────
        if final_answer_text:
            conversation.add_message(
                Message(role=MessageRole.ASSISTANT, content=final_answer_text)
            )

        try:
            await self._repo.save(conversation)
        except Exception:
            logger.exception("Failed to persist conversation %s", conversation.conversation_id)

        yield {
            "event": "done",
            "data": {
                "conversation_id": str(conversation.conversation_id),
                "total_steps": len(state.steps),
            },
        }

