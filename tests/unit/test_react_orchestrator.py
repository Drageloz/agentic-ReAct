"""
Unit tests for the ReAct Orchestrator.
Uses mocked LLM and tool registry — no real network or DB calls.
"""
from __future__ import annotations

import json
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

from app.application.services.react_orchestrator import ReactOrchestrator
from app.application.tools.tool_registry import ToolRegistry
from app.domain.entities.agent import AgentState, StepType
from app.domain.entities.tool import ToolCall, ToolResult


async def _async_gen(*items):
    """Helper: turns a list into an async generator."""
    for item in items:
        yield item


@pytest.fixture
def mock_llm():
    return MagicMock()


@pytest.fixture
def mock_tool_registry():
    registry = MagicMock(spec=ToolRegistry)
    registry.get_definitions.return_value = []
    return registry


@pytest.fixture
def orchestrator(mock_llm, mock_tool_registry):
    return ReactOrchestrator(llm=mock_llm, tool_registry=mock_tool_registry)


@pytest.fixture
def base_state():
    return AgentState(
        session_id=uuid4(),
        user_id="test-user",
        original_query="What shipments are in transit?",
        max_iterations=5,
    )


@pytest.mark.asyncio
async def test_direct_final_answer(orchestrator, mock_llm, base_state):
    """LLM answers directly without calling any tools."""
    mock_llm.chat_completion_stream = AsyncMock(
        return_value=_async_gen("The answer is 42.")
    )
    mock_llm.parse_tool_call = AsyncMock(return_value=None)

    steps = []
    async for step in orchestrator.run(base_state):
        steps.append(step)

    assert len(steps) == 2  # THOUGHT + FINAL_ANSWER
    assert steps[-1].step_type == StepType.FINAL_ANSWER
    assert "42" in steps[-1].content


@pytest.mark.asyncio
async def test_tool_call_then_answer(orchestrator, mock_llm, mock_tool_registry, base_state):
    """LLM calls a tool, gets observation, then answers."""
    tool_sentinel = json.dumps({
        "__tool_call__": True,
        "tool_name": "get_erp_data",
        "arguments": {"action": "list_shipments", "status": "in_transit"},
        "call_id": "call-1",
    })

    # First call: tool request; second call: final answer
    mock_llm.chat_completion_stream = AsyncMock(
        side_effect=[
            _async_gen("I need to check shipments. ", tool_sentinel),
            _async_gen("There are 3 shipments in transit."),
        ]
    )
    mock_llm.parse_tool_call = AsyncMock(
        side_effect=[
            ToolCall(tool_name="get_erp_data", arguments={"action": "list_shipments"}),
            None,
        ]
    )
    mock_tool_registry.execute = AsyncMock(
        return_value=ToolResult(
            call_id=uuid4(),
            tool_name="get_erp_data",
            result=[{"id": "shp-001", "status": "in_transit"}],
        )
    )

    steps = []
    async for step in orchestrator.run(base_state):
        steps.append(step)

    step_types = [s.step_type for s in steps]
    assert StepType.THOUGHT in step_types
    assert StepType.ACTION in step_types
    assert StepType.OBSERVATION in step_types
    assert StepType.FINAL_ANSWER in step_types


@pytest.mark.asyncio
async def test_max_iterations_guard(orchestrator, mock_llm, mock_tool_registry):
    """Agent should stop after max_iterations with a fallback message."""
    tool_sentinel = json.dumps({
        "__tool_call__": True,
        "tool_name": "get_erp_data",
        "arguments": {"action": "list_shipments"},
        "call_id": "call-x",
    })

    # Always returns a tool call — infinite loop candidate
    async def infinite_tool_stream(*args, **kwargs):
        yield tool_sentinel

    mock_llm.chat_completion_stream = AsyncMock(side_effect=lambda **kw: infinite_tool_stream())
    mock_llm.parse_tool_call = AsyncMock(
        return_value=ToolCall(tool_name="get_erp_data", arguments={"action": "list_shipments"})
    )
    mock_tool_registry.execute = AsyncMock(
        return_value=ToolResult(call_id=uuid4(), tool_name="get_erp_data", result=[])
    )

    state = AgentState(
        session_id=uuid4(),
        user_id="test",
        original_query="Loop forever?",
        max_iterations=2,
    )

    steps = []
    async for step in orchestrator.run(state):
        steps.append(step)

    final_steps = [s for s in steps if s.step_type == StepType.FINAL_ANSWER]
    assert len(final_steps) == 1
    assert "maximum" in final_steps[0].content.lower()

