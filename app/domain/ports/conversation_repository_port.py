"""Domain Port for persisting and retrieving Conversations."""
from __future__ import annotations

from abc import ABC, abstractmethod
from uuid import UUID

from app.domain.entities.conversation import Conversation


class ConversationRepositoryPort(ABC):

    @abstractmethod
    async def save(self, conversation: Conversation) -> None:
        """Persist or update a conversation."""

    @abstractmethod
    async def find_by_id(self, conversation_id: UUID) -> Conversation | None:
        """Retrieve a conversation by its primary key."""

    @abstractmethod
    async def find_by_user(self, user_id: str, limit: int = 50) -> list[Conversation]:
        """Retrieve recent conversations for a user."""

