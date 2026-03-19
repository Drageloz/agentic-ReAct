"""
GetConversationHistoryUseCase — retrieves conversation history for a user.
"""
from __future__ import annotations

from uuid import UUID

from app.domain.entities.conversation import Conversation
from app.domain.ports.conversation_repository_port import ConversationRepositoryPort


class GetConversationHistoryUseCase:
    def __init__(self, repo: ConversationRepositoryPort) -> None:
        self._repo = repo

    async def get_by_id(self, conversation_id: UUID) -> Conversation | None:
        return await self._repo.find_by_id(conversation_id)

    async def get_by_user(self, user_id: str, limit: int = 50) -> list[Conversation]:
        return await self._repo.find_by_user(user_id, limit=limit)

