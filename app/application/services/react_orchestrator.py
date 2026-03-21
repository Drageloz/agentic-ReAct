"""
ReAct Orchestrator — the core reasoning loop.

Flow per iteration:
  1. Build prompt with history
  2. Call LLM (streaming)
  3. Detect: text token | tool_call sentinel
  4. If tool_call → execute tool → Observation step → continue loop
  5. If text & no tool_call → emit as FINAL_ANSWER

Yields ReActStep objects as they are produced, enabling SSE streaming.
"""
from __future__ import annotations

import json
import logging
from typing import AsyncIterator

from app.application.tools.tool_registry import ToolRegistry
from app.domain.entities.agent import AgentState, ReActStep, StepType
from app.domain.entities.tool import ToolCall
from app.domain.ports.llm_port import LLMPort

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = """You are an intelligent logistics and finance assistant with access to three tools:

1. **get_erp_data** — Query the ERP system for shipment and user data.
2. **search_regulations** — Search the regulatory knowledge base.
3. **calculate_tax_discrepancy** — Calculate expected tax for a given amount and region, \
and detect discrepancies against a declared tax amount. Use this to validate invoices, \
detect under/over-declarations, and support audit workflows.
- Start with a clear Thought about what you need to do.
- If you need information, call the appropriate tool via function calling.
- After receiving the Observation, continue reasoning until you can give a Final Answer.
- Your Final Answer must be comprehensive, accurate, and based only on retrieved data.

## Rules
- NEVER fabricate shipment IDs, user data, or regulatory content.
- When a question involves both shipment data AND tax validation, chain both tools \
  (first get_erp_data to retrieve amounts, then calculate_tax_discrepancy to validate).
- If the data is not found, say so clearly.
"""


class ReactOrchestrator:
    def __init__(self, llm: LLMPort, tool_registry: ToolRegistry) -> None:
        self._llm = llm
        self._tools = tool_registry

    async def run(self, state: AgentState) -> AsyncIterator[ReActStep]:
        """
        Execute the ReAct loop. Yields each step as it occurs.
        The caller (use case) streams these steps to the client via SSE.
        """
        tool_defs = self._tools.get_definitions()

        while not state.is_done:
            state.increment_iteration()
            messages = self._build_messages(state)

            # ── Accumulate the LLM stream ──────────────────────────────────
            accumulated_text = ""
            tool_call_data: ToolCall | None = None

            async for chunk in self._llm.chat_completion_stream(
                messages=messages,
                tools=tool_defs,
                temperature=0.0,
            ):
                # Detect tool-call sentinel (JSON blob emitted by the adapters)
                if chunk.startswith('{"__tool_call__":'):
                    parsed = await self._llm.parse_tool_call(chunk)
                    if parsed:
                        tool_call_data = parsed
                    continue
                accumulated_text += chunk

            # ── Emit THOUGHT step if we have reasoning text ────────────────
            thought_text = accumulated_text.strip()
            if thought_text:
                thought_step = ReActStep(
                    step_type=StepType.THOUGHT,
                    content=thought_text,
                )
                state.add_step(thought_step)
                yield thought_step

            # ── Tool call branch ───────────────────────────────────────────
            if tool_call_data:
                action_step = ReActStep(
                    step_type=StepType.ACTION,
                    content=f"Calling tool: {tool_call_data.tool_name}",
                    tool_name=tool_call_data.tool_name,
                    tool_input=tool_call_data.arguments,
                )
                state.add_step(action_step)
                yield action_step

                # Execute the tool
                tool_result = await self._tools.execute(tool_call_data)
                observation_text = tool_result.to_observation_text()

                observation_step = ReActStep(
                    step_type=StepType.OBSERVATION,
                    content=observation_text,
                )
                state.add_step(observation_step)
                yield observation_step
                continue  # Next reasoning iteration

            # ── No tool call → this is the final answer ────────────────────
            if thought_text:
                final_step = ReActStep(
                    step_type=StepType.FINAL_ANSWER,
                    content=thought_text,
                )
                state.add_step(final_step)
                yield final_step
                return

        # Max iterations reached
        if not state.final_answer:
            final_step = ReActStep(
                step_type=StepType.FINAL_ANSWER,
                content="I reached the maximum number of reasoning steps without a conclusive answer. Please refine your question.",
            )
            state.add_step(final_step)
            yield final_step

    def _build_messages(self, state: AgentState) -> list[dict]:
        messages: list[dict] = [{"role": "system", "content": SYSTEM_PROMPT}]
        messages.append({"role": "user", "content": state.original_query})

        # Reconstruct history as assistant / tool messages
        for step in state.steps:
            if step.step_type == StepType.THOUGHT:
                messages.append({"role": "assistant", "content": f"Thought: {step.content}"})
            elif step.step_type == StepType.ACTION:
                # Represented as assistant function call intent
                messages.append(
                    {
                        "role": "assistant",
                        "content": f"Action: {step.tool_name}({json.dumps(step.tool_input)})",
                    }
                )
            elif step.step_type == StepType.OBSERVATION:
                messages.append({"role": "user", "content": f"Observation: {step.content}"})

        return messages
