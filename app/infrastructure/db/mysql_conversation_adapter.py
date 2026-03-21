"""
SQL Server Conversation Repository Adapter.
Persists and retrieves Conversation aggregates using T-SQL.

Dialect differences vs MySQL handled here:
  - MERGE  instead of INSERT … ON DUPLICATE KEY UPDATE
  - TOP(n) instead of LIMIT n
  - NVARCHAR / NVARCHAR(MAX) in DDL (see sql/init.sql)
"""
from __future__ import annotations

import json
import logging
from datetime import datetime
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.domain.entities.conversation import Conversation, Message, MessageRole
from app.domain.ports.conversation_repository_port import ConversationRepositoryPort

logger = logging.getLogger(__name__)


class MySQLConversationAdapter(ConversationRepositoryPort):
    """Named MySQLConversationAdapter for backwards-compat; backed by SQL Server."""

    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        self._sf = session_factory

    async def save(self, conversation: Conversation) -> None:
        async with self._sf() as session:
            async with session.begin():
                await session.execute(
                    text(
                        """
                        MERGE conversations AS target
                        USING (SELECT
                            :id          AS id,
                            :user_id     AS user_id,
                            :messages    AS messages,
                            :user_context AS user_context,
                            :rag_id      AS rag_id,
                            :created_at  AS created_at,
                            :updated_at  AS updated_at
                        ) AS source ON target.id = source.id
                        WHEN MATCHED THEN
                            UPDATE SET
                                messages     = source.messages,
                                user_context = source.user_context,
                                rag_id       = source.rag_id,
                                updated_at   = source.updated_at
                        WHEN NOT MATCHED THEN
                            INSERT (id, user_id, messages, user_context, rag_id, created_at, updated_at)
                            VALUES (source.id, source.user_id, source.messages,
                                    source.user_context, source.rag_id,
                                    source.created_at, source.updated_at);
                        """
                    ),
                    {
                        "id": str(conversation.conversation_id),
                        "user_id": conversation.user_id,
                        "messages": json.dumps(
                            [
                                {
                                    "role": m.role.value,
                                    "content": m.content,
                                    "created_at": m.created_at.isoformat(),
                                }
                                for m in conversation.messages
                            ]
                        ),
                        "user_context": json.dumps(conversation.user_context or {}),
                        "rag_id": conversation.rag_id,
                        "created_at": conversation.created_at,
                        "updated_at": conversation.updated_at,
                    },
                )

    async def find_by_id(self, conversation_id: UUID) -> Conversation | None:
        async with self._sf() as session:
            result = await session.execute(
                text(
                    """
                    SELECT TOP(1) id, user_id, messages, user_context, rag_id, created_at, updated_at
                    FROM conversations
                    WHERE id = :id
                    """
                ),
                {"id": str(conversation_id)},
            )
            row = result.mappings().first()
            if row is None:
                return None
            return self._row_to_conversation(dict(row))

    async def find_by_user(self, user_id: str, limit: int = 50) -> list[Conversation]:
        async with self._sf() as session:
            result = await session.execute(
                text(
                    """
                    SELECT TOP(:limit) id, user_id, messages, user_context, rag_id, created_at, updated_at
                    FROM conversations
                    WHERE user_id = :user_id
                    ORDER BY updated_at DESC
                    """
                ),
                {"user_id": user_id, "limit": limit},
            )
            rows = result.mappings().all()
            return [self._row_to_conversation(dict(r)) for r in rows]

    @staticmethod
    def _row_to_conversation(row: dict) -> Conversation:
        raw_messages = json.loads(row["messages"] or "[]")
        messages = [
            Message(
                role=MessageRole(m["role"]),
                content=m["content"],
                created_at=datetime.fromisoformat(
                    m.get("created_at", datetime.utcnow().isoformat())
                ),
            )
            for m in raw_messages
        ]
        return Conversation(
            conversation_id=UUID(row["id"]),
            user_id=row["user_id"],
            messages=messages,
            user_context=json.loads(row["user_context"] or "{}") or None,
            rag_id=row.get("rag_id"),
            created_at=row["created_at"] if isinstance(row["created_at"], datetime)
                       else datetime.fromisoformat(str(row["created_at"])),
            updated_at=row["updated_at"] if isinstance(row["updated_at"], datetime)
                       else datetime.fromisoformat(str(row["updated_at"])),
        )
