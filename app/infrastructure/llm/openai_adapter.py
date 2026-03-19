"""
OpenAI Adapter — implements LLMPort using the openai async client.
Supports streaming and function/tool calling.
"""
from __future__ import annotations

import json
import logging
from typing import Any, AsyncIterator

from openai import AsyncOpenAI

from app.domain.entities.tool import ToolCall, ToolDefinition
from app.domain.ports.llm_port import LLMPort

logger = logging.getLogger(__name__)


def _tool_def_to_openai(td: ToolDefinition) -> dict[str, Any]:
    # Include `strict: True` so the OpenAI client accepts the function tool for
    # auto-parsing. The OpenAI validation requires function tools to be strict
    # when using the beta function-tooling stream APIs.
    return {
        "type": "function",
        "strict": True,
        "function": {
            "name": td.name,
            "description": td.description,
            "parameters": td.parameters,
            "strict": True,
        },
    }


class OpenAIAdapter(LLMPort):
    def __init__(self, api_key: str, model: str, max_tokens: int = 4096) -> None:
        self._client = AsyncOpenAI(api_key=api_key)
        self._model = model
        self._max_tokens = max_tokens

    # ── Non-streaming completion ──────────────────────────────────────────────
    async def chat_completion(
        self,
        messages: list[dict[str, Any]],
        tools: list[ToolDefinition] | None = None,
        temperature: float = 0.0,
    ) -> str:
        kwargs: dict[str, Any] = {
            "model": self._model,
            "messages": messages,
            "temperature": temperature,
            "max_tokens": self._max_tokens,
        }
        if tools:
            kwargs["tools"] = [_tool_def_to_openai(t) for t in tools]
            kwargs["tool_choice"] = "auto"

        response = await self._client.chat.completions.create(**kwargs)
        choice = response.choices[0]

        # If the model wants to call a tool, serialise it as JSON string
        if choice.finish_reason == "tool_calls" and choice.message.tool_calls:
            tc = choice.message.tool_calls[0]
            return json.dumps(
                {
                    "__tool_call__": True,
                    "tool_name": tc.function.name,
                    "arguments": json.loads(tc.function.arguments),
                    "call_id": tc.id,
                }
            )
        return choice.message.content or ""

    # ── Streaming completion ──────────────────────────────────────────────────
    async def chat_completion_stream(
        self,
        messages: list[dict[str, Any]],
        tools: list[ToolDefinition] | None = None,
        temperature: float = 0.0,
    ) -> AsyncIterator[str]:
        kwargs: dict[str, Any] = {
            "model": self._model,
            "messages": messages,
            "temperature": temperature,
            "max_tokens": self._max_tokens,
        }
        if tools:
            kwargs["tools"] = [_tool_def_to_openai(t) for t in tools]
            kwargs["tool_choice"] = "auto"

        # The beta stream API emits typed events — iterate using event.type
        # rather than event.choices (ChunkEvent has no .choices attribute).
        async with self._client.beta.chat.completions.stream(**kwargs) as stream:
            async for event in stream:
                event_type = event.type

                # Text token arriving
                if event_type == "content.delta":
                    yield event.delta

                # Tool call fully assembled — emit sentinel JSON
                elif event_type == "tool_calls.function.arguments.done":
                    try:
                        args = json.loads(event.arguments or "{}")
                    except json.JSONDecodeError:
                        args = {}
                    yield json.dumps(
                        {
                            "__tool_call__": True,
                            "tool_name": event.name,
                            "arguments": args,
                            "call_id": "",
                        }
                    )

    # ── Parse tool call from a serialised response ────────────────────────────
    async def parse_tool_call(self, raw_response: str) -> ToolCall | None:
        try:
            data = json.loads(raw_response)
            if data.get("__tool_call__"):
                return ToolCall(
                    tool_name=data["tool_name"],
                    arguments=data["arguments"],
                )
        except (json.JSONDecodeError, KeyError):
            pass
        return None

