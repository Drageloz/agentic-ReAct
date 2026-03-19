"""Domain Port for RAG (Retrieval-Augmented Generation) searches."""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass


@dataclass
class RAGDocument:
    doc_id: str
    title: str
    content: str
    score: float  # relevance score [0, 1]
    source: str


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
    ) -> list[RAGDocument]:
        """Return the top_k most relevant documents for the given query."""

