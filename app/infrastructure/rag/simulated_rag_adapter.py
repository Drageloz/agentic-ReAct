"""
Simulated RAG Adapter.
Performs keyword-based search over a local regulations.json file.
In production, swap this for a real vector-DB adapter without touching domain code.
"""
from __future__ import annotations

import json
import logging
import re
from pathlib import Path
from typing import Any

from app.domain.ports.rag_port import RAGDocument, RAGPort

logger = logging.getLogger(__name__)

_DATA_FILE = Path(__file__).parent.parent.parent.parent / "data" / "regulations.json"


class SimulatedRAGAdapter(RAGPort):
    """
    Simple TF-IDF-style keyword scorer over a static JSON corpus.
    Documents are loaded once at startup.
    """

    def __init__(self, data_file: Path = _DATA_FILE) -> None:
        self._documents: list[dict[str, Any]] = []
        self._load(data_file)

    def _load(self, path: Path) -> None:
        if not path.exists():
            logger.warning("RAG data file not found at %s — using empty corpus.", path)
            return
        with path.open(encoding="utf-8") as f:
            data = json.load(f)
        self._documents = data if isinstance(data, list) else data.get("documents", [])
        logger.info("RAG corpus loaded: %d documents", len(self._documents))

    async def search(
        self,
        query: str,
        top_k: int = 5,
        rag_session_id: str | None = None,
        metadata_filter: dict[str, Any] | None = None,
    ) -> list[RAGDocument]:
        if not self._documents:
            return []

        # Apply metadata pre-filter (AND semantics) before scoring
        candidates = self._documents
        if metadata_filter:
            candidates = [
                doc for doc in candidates
                if all(
                    str(doc.get(k, "")).lower() == str(v).lower()
                    if not isinstance(v, dict)
                    else self._match_operator(doc.get(k), v)
                    for k, v in metadata_filter.items()
                )
            ]

        tokens = set(re.findall(r"\w+", query.lower()))
        scored: list[tuple[float, dict[str, Any]]] = []

        for doc in candidates:
            text_blob = (doc.get("title", "") + " " + doc.get("content", "")).lower()
            doc_tokens = re.findall(r"\w+", text_blob)
            total = len(doc_tokens) or 1
            score = sum(doc_tokens.count(t) / total for t in tokens)

            # Slight boost for title matches
            title_tokens = re.findall(r"\w+", doc.get("title", "").lower())
            title_matches = sum(1 for t in tokens if t in title_tokens)
            score += title_matches * 0.1
            scored.append((score, doc))

        scored.sort(key=lambda x: x[0], reverse=True)

        return [
            RAGDocument(
                doc_id=str(doc.get("id", i)),
                title=doc.get("title", ""),
                content=doc.get("content", ""),
                score=round(score, 4),
                source=doc.get("source", "regulations.json"),
                metadata={
                    "year": doc.get("year"),
                    "region": doc.get("region"),
                    "category": doc.get("category"),
                    "effective_date": doc.get("effective_date"),
                },
            )
            for i, (score, doc) in enumerate(scored[:top_k])
            if score > 0
        ]

    @staticmethod
    def _match_operator(value: Any, operator: dict) -> bool:
        """Evaluate a Chroma-style operator dict against a scalar value."""
        try:
            if "$eq" in operator:
                return value == operator["$eq"]
            if "$ne" in operator:
                return value != operator["$ne"]
            if "$gte" in operator:
                return float(value) >= float(operator["$gte"])
            if "$gt" in operator:
                return float(value) > float(operator["$gt"])
            if "$lte" in operator:
                return float(value) <= float(operator["$lte"])
            if "$lt" in operator:
                return float(value) < float(operator["$lt"])
            if "$in" in operator:
                return value in operator["$in"]
        except (TypeError, ValueError):
            pass
        return False

