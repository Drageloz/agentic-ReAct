"""
Unit tests — SimulatedRAGAdapter (Parte 2.2)

Cubre:
  - Búsqueda básica devuelve documentos relevantes
  - Metadata filtering por año exacto (requisito explícito de la prueba)
  - Metadata filtering por región
  - Filtro combinado año + región ($and semantics)
  - Operador $gte en metadata filter
  - Sin resultados cuando el filtro no coincide con ningún documento
  - top_k limita correctamente el número de resultados
  - Corpus vacío no lanza excepción
"""
from __future__ import annotations

import json
import tempfile
from pathlib import Path

import pytest

from app.infrastructure.rag.simulated_rag_adapter import SimulatedRAGAdapter


# ── Corpus de prueba ──────────────────────────────────────────────────────────

_CORPUS = [
    {
        "id": "reg-001",
        "title": "EU Customs Code 2013",
        "content": "Union Customs Code establishes customs rules for EU territory.",
        "source": "EUR-Lex",
        "category": "customs",
        "year": 2013,
        "region": "EU",
        "effective_date": "2013-10-09",
    },
    {
        "id": "reg-002",
        "title": "IATA Dangerous Goods 2024",
        "content": "Dangerous goods air transport regulations lithium batteries hazmat.",
        "source": "IATA DGR",
        "category": "dangerous_goods",
        "year": 2024,
        "region": "GLOBAL",
        "effective_date": "2024-01-01",
    },
    {
        "id": "reg-003",
        "title": "EU Common External Tariff 2024",
        "content": "Import duties customs tariff EU combined nomenclature 2024.",
        "source": "EU TARIC",
        "category": "customs",
        "year": 2024,
        "region": "EU",
        "effective_date": "2024-01-01",
    },
    {
        "id": "reg-004",
        "title": "CMR Convention 1978",
        "content": "Carrier liability road freight international carriage convention.",
        "source": "UNECE CMR",
        "category": "carrier_liability",
        "year": 1978,
        "region": "EUROPE",
        "effective_date": "1978-12-28",
    },
    {
        "id": "reg-005",
        "title": "EU Dual-Use Export Controls 2021",
        "content": "Export controls dual-use goods military civil regulation 2021.",
        "source": "EU 2021/821",
        "category": "export_controls",
        "year": 2021,
        "region": "EU",
        "effective_date": "2021-09-09",
    },
]


@pytest.fixture
def adapter(tmp_path: Path) -> SimulatedRAGAdapter:
    """Adapter cargado con el corpus de prueba en un archivo temporal."""
    data_file = tmp_path / "regulations.json"
    data_file.write_text(json.dumps({"documents": _CORPUS}), encoding="utf-8")
    return SimulatedRAGAdapter(data_file=data_file)


@pytest.fixture
def empty_adapter(tmp_path: Path) -> SimulatedRAGAdapter:
    data_file = tmp_path / "empty.json"
    data_file.write_text(json.dumps({"documents": []}), encoding="utf-8")
    return SimulatedRAGAdapter(data_file=data_file)


# ── Tests básicos ─────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_basic_search_returns_relevant_documents(adapter):
    """Una búsqueda de 'customs' debe devolver documentos con ese término."""
    results = await adapter.search("customs EU import duties")
    assert len(results) > 0
    titles = [r.title for r in results]
    assert any("Customs" in t or "Tariff" in t for t in titles)


@pytest.mark.asyncio
async def test_top_k_limits_results(adapter):
    """top_k=2 nunca debe devolver más de 2 documentos."""
    results = await adapter.search("regulation EU", top_k=2)
    assert len(results) <= 2


@pytest.mark.asyncio
async def test_empty_corpus_returns_empty_list(empty_adapter):
    """Un corpus vacío no lanza excepción y devuelve lista vacía."""
    results = await empty_adapter.search("customs 2024")
    assert results == []


@pytest.mark.asyncio
async def test_results_have_required_fields(adapter):
    """Cada RAGDocument debe tener doc_id, title, content, score y metadata."""
    results = await adapter.search("customs")
    assert len(results) > 0
    for doc in results:
        assert doc.doc_id
        assert doc.title
        assert doc.content
        assert doc.score >= 0
        assert "year" in doc.metadata
        assert "region" in doc.metadata
        assert "category" in doc.metadata


# ── Metadata Filtering (Parte 2.2 — requisito explícito) ─────────────────────

@pytest.mark.asyncio
async def test_metadata_filter_year_exact_returns_only_2024_docs(adapter):
    """
    Parte 2.2 — Metadata Filtering por año exacto.
    Filtrando year=2024 solo deben aparecer reg-002 y reg-003.
    """
    # Query con términos que aparecen en los documentos de 2024
    results = await adapter.search("dangerous goods tariff 2024", metadata_filter={"year": 2024}, top_k=10)
    assert len(results) > 0
    for doc in results:
        assert doc.metadata["year"] == 2024, (
            f"Documento '{doc.title}' tiene year={doc.metadata['year']}, esperado 2024"
        )


@pytest.mark.asyncio
async def test_metadata_filter_excludes_older_documents(adapter):
    """
    Parte 2.2 — El filtro de año evita ruido de documentos históricos.
    Con year=2024, reg-001 (2013) y reg-004 (1978) no deben aparecer.
    """
    results = await adapter.search("customs EU", metadata_filter={"year": 2024}, top_k=10)
    doc_ids = [r.doc_id for r in results]
    assert "reg-001" not in doc_ids, "reg-001 (2013) no debería estar en resultados filtrados a 2024"
    assert "reg-004" not in doc_ids, "reg-004 (1978) no debería estar en resultados filtrados a 2024"


@pytest.mark.asyncio
async def test_metadata_filter_by_region(adapter):
    """Filtrar por region=EU debe excluir reg-002 (GLOBAL) y reg-004 (EUROPE)."""
    results = await adapter.search("regulation", metadata_filter={"region": "EU"}, top_k=10)
    for doc in results:
        assert doc.metadata["region"] == "EU"


@pytest.mark.asyncio
async def test_metadata_filter_combined_year_and_region(adapter):
    """
    Filtro combinado year=2024 AND region=EU → solo reg-003 debe aparecer.
    Demuestra $and semantics del SimulatedRAGAdapter.
    """
    results = await adapter.search(
        "customs tariff",
        metadata_filter={"year": 2024, "region": "EU"},
        top_k=10,
    )
    assert len(results) >= 1
    for doc in results:
        assert doc.metadata["year"] == 2024
        assert doc.metadata["region"] == "EU"


@pytest.mark.asyncio
async def test_metadata_filter_no_match_returns_empty(adapter):
    """Un filtro que no coincide con ningún documento devuelve lista vacía."""
    results = await adapter.search("regulation", metadata_filter={"year": 1900}, top_k=10)
    assert results == []


@pytest.mark.asyncio
async def test_metadata_filter_gte_operator(adapter):
    """
    Operador $gte — solo documentos con year >= 2021 (reg-002, reg-003, reg-005).
    """
    results = await adapter.search(
        "regulation",
        metadata_filter={"year": {"$gte": 2021}},
        top_k=10,
    )
    assert len(results) > 0
    for doc in results:
        assert doc.metadata["year"] >= 2021, (
            f"Documento '{doc.title}' tiene year={doc.metadata['year']}, esperado >= 2021"
        )
    doc_ids = [r.doc_id for r in results]
    assert "reg-001" not in doc_ids  # 2013
    assert "reg-004" not in doc_ids  # 1978


@pytest.mark.asyncio
async def test_metadata_filter_category(adapter):
    """Filtrar por category=customs devuelve solo documentos de aduanas."""
    results = await adapter.search(
        "import rules",
        metadata_filter={"category": "customs"},
        top_k=10,
    )
    for doc in results:
        assert doc.metadata["category"] == "customs"


@pytest.mark.asyncio
async def test_no_filter_returns_multiple_years(adapter):
    """
    Test contrastante — sin filtro la búsqueda devuelve documentos de distintos años,
    demostrando que el filtro es necesario para evitar ruido.
    """
    results = await adapter.search("customs EU regulation", top_k=10)
    years = {doc.metadata["year"] for doc in results}
    # Sin filtro deben aparecer documentos de más de un año
    assert len(years) > 1, "Sin filtro deberían aparecer documentos de múltiples años"

