"""Domain Ports (interfaces) for LLM providers."""
from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any, AsyncIterator

from app.domain.entities.tool import ToolDefinition, ToolCall


class LLMPort(ABC):
    """
    Abstract port for any LLM provider (OpenAI, Anthropic Claude, etc.).
    All infrastructure adapters MUST implement this interface.
    """

    @abstractmethod
    async def chat_completion(
        self,
        messages: list[dict[str, Any]],
        tools: list[ToolDefinition] | None = None,
        temperature: float = 0.0,
    ) -> str:
        """
        Perform a standard (non-streaming) chat completion.
        Returns the assistant message content as a string.
        """

    @abstractmethod
    async def chat_completion_stream(
        self,
        messages: list[dict[str, Any]],
        tools: list[ToolDefinition] | None = None,
        temperature: float = 0.0,
    ) -> AsyncIterator[str]:
        """
        Perform a streaming chat completion.
        Yields token chunks as they arrive from the provider.
        May also yield special sentinel tokens to signal tool calls.
        """

    @abstractmethod
    async def parse_tool_call(
        self,
        raw_response: str,
    ) -> ToolCall | None:
        """
        Given a raw LLM response (or the last chunk), extract a ToolCall
        if the model decided to invoke a tool.  Returns None otherwise.
        """

