"""
Pydantic schemas for the Chat API.
"""
from __future__ import annotations

from typing import Any, Optional
from uuid import UUID

from pydantic import BaseModel, Field


class ChatRequest(BaseModel):
    query: str = Field(..., min_length=1, max_length=4096, description="User's natural language query")
    user_id: str = Field(..., min_length=1, max_length=128)
    conversation_id: Optional[UUID] = Field(None, description="Continue an existing conversation")
    user_context: Optional[dict[str, Any]] = Field(None, description="Extra user context (e.g. role, language)")
    rag_id: Optional[str] = Field(None, description="RAG session / document set ID")

    model_config = {
        "json_schema_extra": {
            "example": {
                "query": "What is the status of shipment SHP-001?",
                "user_id": "user-42",
                "conversation_id": None,
                "user_context": {"language": "en", "role": "logistics_manager"},
            }
        }
    }


class SSEEvent(BaseModel):
    event: str
    data: Any

    def to_sse_string(self) -> str:
        import json
        return f"event: {self.event}\ndata: {json.dumps(self.data, default=str)}\n\n"

