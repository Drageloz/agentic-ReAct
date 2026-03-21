"""Domain Port for RAG (Retrieval-Augmented Generation) searches."""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any


@dataclass
class RAGDocument:
    doc_id: str
    title: str
    content: str
    score: float  # relevance score [0, 1]
    source: str
    metadata: dict[str, Any] = field(default_factory=dict)  # year, region, category …


class RAGPort(ABC):
    """
    Abstract port for regulation / knowledge-base searches.
    Can be backed by a vector DB, ElasticSearch, or a simple in-memory index.
    """

    @abstractmethod
    async def search(
        self,
        query: str,
        top_k: int = 5,
        rag_session_id: str | None = None,
        metadata_filter: dict[str, Any] | None = None,
    ) -> list[RAGDocument]:
        """
        Return the top_k most relevant documents for the given query.

        Args:
            query: Natural language search string.
            top_k: Maximum number of documents to return.
            rag_session_id: Optional session context (unused in basic impls).
            metadata_filter: Key-value pairs for hard filtering before ranking.
                             Example: {"year": 2024, "category": "customs"}
                             All provided keys must match (AND semantics).
        """
