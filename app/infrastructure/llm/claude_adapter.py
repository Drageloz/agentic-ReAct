"""
Anthropic Claude Adapter — implements LLMPort using the anthropic async client.
Supports streaming and tool_use (function calling).
"""
from __future__ import annotations

import json
import logging
from typing import Any, AsyncIterator

import anthropic

from app.domain.entities.tool import ToolCall, ToolDefinition
from app.domain.ports.llm_port import LLMPort

logger = logging.getLogger(__name__)


def _tool_def_to_anthropic(td: ToolDefinition) -> dict[str, Any]:
    return {
        "name": td.name,
        "description": td.description,
        "input_schema": td.parameters,
    }


def _convert_messages_for_claude(messages: list[dict[str, Any]]) -> tuple[str, list[dict[str, Any]]]:
    """
    Anthropic separates 'system' prompt from the messages list.
    Returns (system_prompt, user_assistant_messages).
    """
    system_parts: list[str] = []
    rest: list[dict[str, Any]] = []
    for m in messages:
        if m["role"] == "system":
            system_parts.append(m["content"])
        else:
            rest.append(m)
    return "\n\n".join(system_parts), rest


class ClaudeAdapter(LLMPort):
    def __init__(self, api_key: str, model: str, max_tokens: int = 4096) -> None:
        self._client = anthropic.AsyncAnthropic(api_key=api_key)
        self._model = model
        self._max_tokens = max_tokens

    async def chat_completion(
        self,
        messages: list[dict[str, Any]],
        tools: list[ToolDefinition] | None = None,
        temperature: float = 0.0,
    ) -> str:
        system_prompt, conv_messages = _convert_messages_for_claude(messages)

        kwargs: dict[str, Any] = {
            "model": self._model,
            "max_tokens": self._max_tokens,
            "temperature": temperature,
            "messages": conv_messages,
        }
        if system_prompt:
            kwargs["system"] = system_prompt
        if tools:
            kwargs["tools"] = [_tool_def_to_anthropic(t) for t in tools]

        response = await self._client.messages.create(**kwargs)

        for block in response.content:
            if block.type == "tool_use":
                return json.dumps(
                    {
                        "__tool_call__": True,
                        "tool_name": block.name,
                        "arguments": block.input,
                        "call_id": block.id,
                    }
                )
            if block.type == "text":
                return block.text
        return ""

    async def chat_completion_stream(
        self,
        messages: list[dict[str, Any]],
        tools: list[ToolDefinition] | None = None,
        temperature: float = 0.0,
    ) -> AsyncIterator[str]:
        system_prompt, conv_messages = _convert_messages_for_claude(messages)

        kwargs: dict[str, Any] = {
            "model": self._model,
            "max_tokens": self._max_tokens,
            "temperature": temperature,
            "messages": conv_messages,
        }
        if system_prompt:
            kwargs["system"] = system_prompt
        if tools:
            kwargs["tools"] = [_tool_def_to_anthropic(t) for t in tools]

        tool_use_buffer: dict[str, Any] = {}

        async with self._client.messages.stream(**kwargs) as stream:
            async for event in stream:
                event_type = event.type

                if event_type == "content_block_start":
                    if hasattr(event, "content_block") and event.content_block.type == "tool_use":
                        tool_use_buffer = {
                            "id": event.content_block.id,
                            "name": event.content_block.name,
                            "input_json": "",
                        }

                elif event_type == "content_block_delta":
                    delta = event.delta
                    if delta.type == "text_delta":
                        yield delta.text
                    elif delta.type == "input_json_delta":
                        tool_use_buffer["input_json"] = tool_use_buffer.get("input_json", "") + delta.partial_json

                elif event_type == "content_block_stop" and tool_use_buffer:
                    try:
                        args = json.loads(tool_use_buffer.get("input_json") or "{}")
                    except json.JSONDecodeError:
                        args = {}
                    yield json.dumps(
                        {
                            "__tool_call__": True,
                            "tool_name": tool_use_buffer["name"],
                            "arguments": args,
                            "call_id": tool_use_buffer["id"],
                        }
                    )
                    tool_use_buffer = {}

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

