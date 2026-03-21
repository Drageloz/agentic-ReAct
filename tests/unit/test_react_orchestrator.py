"""
Unit tests — ReAct Orchestrator (Parte 2.1)

Covers:
  - Respuesta directa sin herramientas
  - Encadenamiento get_erp_data → calculate_tax_discrepancy  ← requisito explícito
  - Iteración única con una sola herramienta
  - Guard de max_iterations (loop infinito)
  - Paso OBSERVATION contiene el resultado de la herramienta
"""
from __future__ import annotations

import json
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest

from app.application.services.react_orchestrator import ReactOrchestrator
from app.application.tools.tool_registry import ToolRegistry
from app.domain.entities.agent import AgentState, StepType
from app.domain.entities.tool import ToolCall, ToolResult


# ── Helpers ───────────────────────────────────────────────────────────────────

async def _stream(*chunks: str):
    """Convierte una secuencia de strings en un async generator."""
    for chunk in chunks:
        yield chunk


def _make_stream(*chunks: str):
    """
    Devuelve una función regular (no coroutine) que retorna un async generator.
    chat_completion_stream NO es awaitable — se llama directamente y devuelve
    un AsyncIterator, por lo que el mock debe ser un MagicMock con side_effect,
    no un AsyncMock.
    """
    async def _gen():
        for chunk in chunks:
            yield chunk
    return _gen()


def _tool_sentinel(tool_name: str, arguments: dict) -> str:
    """Devuelve el JSON sentinel que el adaptador emite cuando el LLM llama una herramienta."""
    return json.dumps({
        "__tool_call__": True,
        "tool_name": tool_name,
        "arguments": arguments,
        "call_id": str(uuid4()),
    })


def _make_state(query: str = "test query", max_iterations: int = 5) -> AgentState:
    return AgentState(
        session_id=uuid4(),
        user_id="user-001",
        original_query=query,
        max_iterations=max_iterations,
    )


# ── Fixtures ──────────────────────────────────────────────────────────────────

@pytest.fixture
def mock_llm():
    return MagicMock()


@pytest.fixture
def mock_registry():
    registry = MagicMock(spec=ToolRegistry)
    registry.get_definitions.return_value = []
    return registry


@pytest.fixture
def orchestrator(mock_llm, mock_registry):
    return ReactOrchestrator(llm=mock_llm, tool_registry=mock_registry)


# ── Tests ─────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_direct_answer_emits_thought_and_final_answer(orchestrator, mock_llm):
    """El LLM responde directamente sin invocar ninguna herramienta."""
    mock_llm.chat_completion_stream = MagicMock(
        return_value=_make_stream("Shipment shp-001 is in transit from Madrid to Paris.")
    )
    mock_llm.parse_tool_call = AsyncMock(return_value=None)

    steps = []
    async for step in orchestrator.run(_make_state("Status of shp-001?")):
        steps.append(step)

    types = [s.step_type for s in steps]
    assert StepType.THOUGHT in types
    assert StepType.FINAL_ANSWER in types
    assert StepType.ACTION not in types
    assert "Madrid" in steps[-1].content


@pytest.mark.asyncio
async def test_single_tool_call_produces_full_react_cycle(orchestrator, mock_llm, mock_registry):
    """
    Una llamada a get_erp_data produce el ciclo completo:
    THOUGHT → ACTION → OBSERVATION → FINAL_ANSWER
    """
    sentinel = _tool_sentinel("get_erp_data", {"action": "get_shipment", "shipment_id": "shp-001"})

    mock_llm.chat_completion_stream = MagicMock(side_effect=[
        _make_stream("I need to query the ERP. ", sentinel),
        _make_stream("The shipment is in transit."),
    ])
    mock_llm.parse_tool_call = AsyncMock(side_effect=[
        ToolCall(tool_name="get_erp_data", arguments={"action": "get_shipment", "shipment_id": "shp-001"}),
        None,
    ])
    mock_registry.execute = AsyncMock(return_value=ToolResult(
        call_id=uuid4(),
        tool_name="get_erp_data",
        result={"id": "shp-001", "status": "in_transit", "origin": "Madrid, ES"},
    ))

    steps = []
    async for step in orchestrator.run(_make_state("Status of shp-001?")):
        steps.append(step)

    types = [s.step_type for s in steps]
    assert StepType.THOUGHT in types
    assert StepType.ACTION in types
    assert StepType.OBSERVATION in types
    assert StepType.FINAL_ANSWER in types

    action_step = next(s for s in steps if s.step_type == StepType.ACTION)
    assert action_step.tool_name == "get_erp_data"

    obs_step = next(s for s in steps if s.step_type == StepType.OBSERVATION)
    assert "in_transit" in obs_step.content


@pytest.mark.asyncio
async def test_tool_chaining_erp_then_tax(orchestrator, mock_llm, mock_registry):
    """
    Encadenamiento get_erp_data → calculate_tax_discrepancy  (Parte 2.1 requisito core).

    El agente primero consulta el ERP y luego valida el impuesto con los datos obtenidos.
    Se verifican ACTION steps para ambas herramientas en el orden correcto.
    """
    erp_sentinel = _tool_sentinel(
        "get_erp_data",
        {"action": "get_shipment", "shipment_id": "shp-001"},
    )
    tax_sentinel = _tool_sentinel(
        "calculate_tax_discrepancy",
        {"amount": 1000.0, "region": "ES", "declared_tax": 150.0},
    )

    mock_llm.chat_completion_stream = MagicMock(side_effect=[
        _make_stream("First I'll get the shipment data. ", erp_sentinel),
        _make_stream("Now I'll validate the tax. ", tax_sentinel),
        _make_stream("Tax is UNDER_DECLARED. Discrepancy of 60 EUR detected."),
    ])
    mock_llm.parse_tool_call = AsyncMock(side_effect=[
        ToolCall(tool_name="get_erp_data", arguments={"action": "get_shipment", "shipment_id": "shp-001"}),
        ToolCall(tool_name="calculate_tax_discrepancy", arguments={"amount": 1000.0, "region": "ES", "declared_tax": 150.0}),
        None,
    ])
    mock_registry.execute = AsyncMock(side_effect=[
        ToolResult(
            call_id=uuid4(),
            tool_name="get_erp_data",
            result={"id": "shp-001", "origin": "Madrid, ES", "weight_kg": 12.5},
        ),
        ToolResult(
            call_id=uuid4(),
            tool_name="calculate_tax_discrepancy",
            result={
                "status": "UNDER_DECLARED",
                "expected_tax": 210.0,
                "declared_tax": 150.0,
                "discrepancy": -60.0,
                "alert": True,
                "region": "ES",
            },
        ),
    ])

    steps = []
    async for step in orchestrator.run(_make_state("Validate tax for shp-001, declared 150 EUR on 1000 EUR invoice from Spain")):
        steps.append(step)

    action_steps = [s for s in steps if s.step_type == StepType.ACTION]
    assert len(action_steps) == 2
    assert action_steps[0].tool_name == "get_erp_data"
    assert action_steps[1].tool_name == "calculate_tax_discrepancy"

    observations = [s for s in steps if s.step_type == StepType.OBSERVATION]
    assert len(observations) == 2
    assert "UNDER_DECLARED" in observations[1].content

    final = next(s for s in steps if s.step_type == StepType.FINAL_ANSWER)
    assert final.content


@pytest.mark.asyncio
async def test_tool_result_error_is_handled_gracefully(orchestrator, mock_llm, mock_registry):
    """Cuando una herramienta falla, el agente recibe el error en OBSERVATION y continúa."""
    sentinel = _tool_sentinel("get_erp_data", {"action": "get_shipment", "shipment_id": "shp-999"})

    mock_llm.chat_completion_stream = MagicMock(side_effect=[
        _make_stream(sentinel),
        _make_stream("Shipment shp-999 was not found in the ERP system."),
    ])
    mock_llm.parse_tool_call = AsyncMock(side_effect=[
        ToolCall(tool_name="get_erp_data", arguments={"action": "get_shipment", "shipment_id": "shp-999"}),
        None,
    ])
    mock_registry.execute = AsyncMock(return_value=ToolResult(
        call_id=uuid4(),
        tool_name="get_erp_data",
        result=None,
        is_error=True,
        error_message="Shipment shp-999 not found.",
    ))

    steps = []
    async for step in orchestrator.run(_make_state("Get shp-999")):
        steps.append(step)

    obs = next(s for s in steps if s.step_type == StepType.OBSERVATION)
    assert "ERROR" in obs.content or "not found" in obs.content.lower()

    types = [s.step_type for s in steps]
    assert StepType.FINAL_ANSWER in types


@pytest.mark.asyncio
async def test_max_iterations_guard_stops_infinite_loop(orchestrator, mock_llm, mock_registry):
    """El agente debe detenerse tras max_iterations y emitir un FINAL_ANSWER de fallback."""
    sentinel = _tool_sentinel("get_erp_data", {"action": "list_shipments"})

    def always_tool(**kw):
        return _make_stream(sentinel)

    mock_llm.chat_completion_stream = MagicMock(side_effect=always_tool)
    mock_llm.parse_tool_call = AsyncMock(
        return_value=ToolCall(tool_name="get_erp_data", arguments={"action": "list_shipments"})
    )
    mock_registry.execute = AsyncMock(return_value=ToolResult(
        call_id=uuid4(), tool_name="get_erp_data", result=[]
    ))

    state = _make_state(max_iterations=2)
    steps = []
    async for step in orchestrator.run(state):
        steps.append(step)

    final_steps = [s for s in steps if s.step_type == StepType.FINAL_ANSWER]
    assert len(final_steps) == 1
    assert "maximum" in final_steps[0].content.lower() or final_steps[0].content


@pytest.mark.asyncio
async def test_registry_execute_called_with_correct_tool_name(orchestrator, mock_llm, mock_registry):
    """El ToolRegistry recibe exactamente el tool_name que el LLM solicitó."""
    sentinel = _tool_sentinel("calculate_tax_discrepancy", {"amount": 500.0, "region": "DE"})

    mock_llm.chat_completion_stream = MagicMock(side_effect=[
        _make_stream(sentinel),
        _make_stream("Tax for Germany is correct."),
    ])
    mock_llm.parse_tool_call = AsyncMock(side_effect=[
        ToolCall(tool_name="calculate_tax_discrepancy", arguments={"amount": 500.0, "region": "DE"}),
        None,
    ])
    mock_registry.execute = AsyncMock(return_value=ToolResult(
        call_id=uuid4(),
        tool_name="calculate_tax_discrepancy",
        result={"status": "OK", "expected_tax": 95.0, "region": "DE"},
    ))

    async for _ in orchestrator.run(_make_state("Calculate tax for 500 EUR in Germany")):
        pass

    mock_registry.execute.assert_called_once()
    call_arg: ToolCall = mock_registry.execute.call_args[0][0]
    assert call_arg.tool_name == "calculate_tax_discrepancy"
    assert call_arg.arguments["region"] == "DE"

