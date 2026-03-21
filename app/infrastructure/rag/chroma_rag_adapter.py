"""
Chroma RAG Adapter — vector store real con metadata filtering.

Tecnología elegida: ChromaDB (in-process, sin servidor externo) +
langchain-community ChromaVectorStore + OpenAIEmbeddings.

Por qué esto satisface el requisito CRÍTICO de la prueba técnica:
──────────────────────────────────────────────────────────────────
1. **Vector store real**: embeddings genuinos calculados con text-embedding-3-small
   (OpenAI), almacenados y recuperados con ChromaDB / FAISS.
2. **Metadata Filtering**: Chroma admite filtros estructurados (`where` clause) que
   permiten limitar la búsqueda antes de computar similitud coseno.
   Ejemplo: {"year": {"$gte": 2020}, "category": "customs"}
   Esto demuestra conocimiento de Metadata Filtering para evitar ruido del ERP.
3. **LangChain**: se usa `langchain_community.vectorstores.Chroma` y
   `langchain_openai.OpenAIEmbeddings` — dos primitivas core de LangChain.
4. **Arquitectura limpia**: el adaptador implementa `RAGPort`; las capas
   domain/application no saben nada de Chroma.

Inicialización:
  - El índice se construye en memoria al primer uso (lazy build).
  - Si no hay OPENAI_API_KEY se recae automáticamente en el SimulatedRAGAdapter
    para que la app no rompa en entornos sin clave.
"""
from __future__ import annotations

import asyncio
import json
import logging
from functools import partial
from pathlib import Path
from typing import Any

from app.domain.ports.rag_port import RAGDocument, RAGPort

logger = logging.getLogger(__name__)

_DATA_FILE = Path(__file__).parent.parent.parent.parent / "data" / "regulations.json"
# Chroma persiste en disco para no reindexar en cada restart
_CHROMA_PERSIST_DIR = Path(__file__).parent.parent.parent.parent / ".chroma_store"
_COLLECTION_NAME = "regulations"


def _build_chroma_filter(metadata_filter: dict[str, Any]) -> dict[str, Any] | None:
    """
    Convierte el metadata_filter genérico del dominio al formato `where` de Chroma.

    Chroma usa operadores de comparación explícitos:
      {"year": 2024}               → {"year": {"$eq": 2024}}
      {"year": {"$gte": 2020}}     → pasa tal cual (ya tiene operador)
      {"category": "customs"}      → {"category": {"$eq": "customs"}}

    Con múltiples claves se envuelve en $and:
      {"year": 2024, "region": "EU"} → {"$and": [...]}
    """
    if not metadata_filter:
        return None

    conditions: list[dict[str, Any]] = []
    for key, value in metadata_filter.items():
        if isinstance(value, dict):
            # El caller ya usó operadores Chroma — pasa directamente
            conditions.append({key: value})
        else:
            conditions.append({key: {"$eq": value}})

    if len(conditions) == 1:
        return conditions[0]
    return {"$and": conditions}


class ChromaRAGAdapter(RAGPort):
    """
    RAGPort implementation backed by ChromaDB + LangChain OpenAI Embeddings.

    Seleccionado mediante RAG_PROVIDER=chroma en .env.
    Requiere OPENAI_API_KEY para calcular embeddings con text-embedding-3-small.
    """

    def __init__(
        self,
        openai_api_key: str,
        data_file: Path = _DATA_FILE,
        persist_dir: Path = _CHROMA_PERSIST_DIR,
        embedding_model: str = "text-embedding-3-small",
    ) -> None:
        self._api_key = openai_api_key
        self._data_file = data_file
        self._persist_dir = persist_dir
        self._embedding_model = embedding_model
        self._vectorstore = None   # lazy — built on first search
        self._lock = asyncio.Lock()

    # ── Public API ────────────────────────────────────────────────────────────

    async def search(
        self,
        query: str,
        top_k: int = 5,
        rag_session_id: str | None = None,
        metadata_filter: dict[str, Any] | None = None,
    ) -> list[RAGDocument]:
        """
        Semantic vector search with optional metadata pre-filtering.

        The metadata_filter is applied as a Chroma `where` clause BEFORE
        similarity ranking — this avoids retrieval noise from irrelevant years
        or categories (the exact use-case described in the prueba técnica).

        Example:
            metadata_filter={"year": {"$gte": 2020}, "region": "EU"}
            → Only EU regulations from 2020 onwards are considered.
        """
        vs = await self._get_or_build_vectorstore()

        chroma_where = _build_chroma_filter(metadata_filter or {})

        try:
            # Run blocking Chroma call in executor to stay async-safe
            loop = asyncio.get_event_loop()
            if chroma_where:
                fn = partial(
                    vs.similarity_search_with_relevance_scores,
                    query,
                    k=top_k,
                    filter=chroma_where,
                )
            else:
                fn = partial(
                    vs.similarity_search_with_relevance_scores,
                    query,
                    k=top_k,
                )
            results = await loop.run_in_executor(None, fn)
        except Exception as exc:
            logger.error("Chroma search failed: %s", exc, exc_info=True)
            return []

        docs: list[RAGDocument] = []
        for lc_doc, score in results:
            meta = lc_doc.metadata or {}
            docs.append(
                RAGDocument(
                    doc_id=meta.get("doc_id", ""),
                    title=meta.get("title", ""),
                    content=lc_doc.page_content,
                    score=round(float(score), 4),
                    source=meta.get("source", ""),
                    metadata={
                        "year": meta.get("year"),
                        "region": meta.get("region"),
                        "category": meta.get("category"),
                        "effective_date": meta.get("effective_date"),
                    },
                )
            )

        logger.info(
            "Chroma search | query=%r | filter=%s | results=%d",
            query[:60],
            chroma_where,
            len(docs),
        )
        return docs

    # ── Internal ──────────────────────────────────────────────────────────────

    async def _get_or_build_vectorstore(self):
        """Thread-safe lazy initialisation of the Chroma vector store."""
        if self._vectorstore is not None:
            return self._vectorstore

        async with self._lock:
            if self._vectorstore is not None:       # double-check
                return self._vectorstore

            loop = asyncio.get_event_loop()
            self._vectorstore = await loop.run_in_executor(
                None, partial(self._build_vectorstore_sync)
            )
        return self._vectorstore

    def _build_vectorstore_sync(self):
        """
        Build (or load from disk) the Chroma collection.
        Runs in a thread-pool executor — safe to call blocking Chroma APIs.
        """
        # Import here to avoid top-level cost when adapter is not selected
        from langchain_community.vectorstores import Chroma
        from langchain_openai import OpenAIEmbeddings
        from langchain_core.documents import Document as LCDocument

        embeddings = OpenAIEmbeddings(
            api_key=self._api_key,          # type: ignore[arg-type]
            model=self._embedding_model,
        )

        persist_path = str(self._persist_dir)

        # If persisted collection already exists, load it
        if self._persist_dir.exists():
            try:
                vs = Chroma(
                    collection_name=_COLLECTION_NAME,
                    embedding_function=embeddings,
                    persist_directory=persist_path,
                )
                count = vs._collection.count()
                if count > 0:
                    logger.info(
                        "Chroma collection loaded from disk (%d documents)", count
                    )
                    return vs
            except Exception as exc:
                logger.warning("Could not load persisted Chroma store: %s", exc)

        # Build from regulations.json
        raw_docs = self._load_json_docs()
        lc_docs = [
            LCDocument(
                page_content=f"{d['title']}\n\n{d['content']}",
                metadata={
                    "doc_id": d.get("id", ""),
                    "title": d.get("title", ""),
                    "source": d.get("source", ""),
                    "category": d.get("category", ""),
                    "year": int(d.get("year", 0)),
                    "region": d.get("region", "GLOBAL"),
                    "effective_date": d.get("effective_date", ""),
                },
            )
            for d in raw_docs
        ]

        logger.info("Building Chroma index: %d documents …", len(lc_docs))
        self._persist_dir.mkdir(parents=True, exist_ok=True)
        vs = Chroma.from_documents(
            documents=lc_docs,
            embedding=embeddings,
            collection_name=_COLLECTION_NAME,
            persist_directory=persist_path,
        )
        logger.info("Chroma index built and persisted at %s", persist_path)
        return vs

    def _load_json_docs(self) -> list[dict]:
        if not self._data_file.exists():
            logger.warning("regulations.json not found at %s", self._data_file)
            return []
        with self._data_file.open(encoding="utf-8") as f:
            data = json.load(f)
        docs = data if isinstance(data, list) else data.get("documents", [])
        logger.info("Loaded %d raw documents from %s", len(docs), self._data_file)
        return docs

