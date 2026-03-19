"""
Domain Entities: Conversation and Message.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Optional
from uuid import UUID, uuid4


class MessageRole(str, Enum):
    USER = "user"
    ASSISTANT = "assistant"
    SYSTEM = "system"
    TOOL = "tool"


@dataclass
class Message:
    role: MessageRole
    content: str
    created_at: datetime = field(default_factory=datetime.utcnow)
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class Conversation:
    conversation_id: UUID
    user_id: str
    messages: list[Message] = field(default_factory=list)
    user_context: Optional[dict[str, Any]] = None  # Extra user profile / session data
    rag_id: Optional[str] = None                   # Linked RAG session/document ID
    created_at: datetime = field(default_factory=datetime.utcnow)
    updated_at: datetime = field(default_factory=datetime.utcnow)

    def add_message(self, message: Message) -> None:
        self.messages.append(message)
        self.updated_at = datetime.utcnow()

    def to_llm_messages(self) -> list[dict[str, str]]:
        """Convert to the format expected by LLM APIs."""
        return [
            {"role": m.role.value, "content": m.content}
            for m in self.messages
        ]

