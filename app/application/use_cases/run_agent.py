"""
RunAgentUseCase — entry point for processing a chat request.

Orchestrates:
  1. Load or create Conversation
  2. Add user message
  3. Run ReactOrchestrator (streaming)
  4. Persist updated Conversation
  5. Yield SSE-ready dicts
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

        async for step in self._orchestrator.run(state):
            event_data = step.to_dict()
            yield {"event": step.step_type.value, "data": event_data}

            if step.step_type == StepType.FINAL_ANSWER:
                final_answer_text = step.content

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

