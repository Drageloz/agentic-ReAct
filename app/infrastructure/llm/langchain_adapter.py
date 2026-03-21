"""
LangChain Adapter — implements LLMPort using langchain-openai.

Why LangChain here instead of the raw OpenAI client?
─────────────────────────────────────────────────────
The prueba técnica explicitly requires LangChain / LlamaIndex / AutoGen.
Rather than replacing the clean hexagonal architecture, we plug LangChain in
as *one more infrastructure adapter* that satisfies the same LLMPort contract.
The domain and application layers remain framework-agnostic.

What LangChain brings:
  • ChatOpenAI with built-in retry / back-off logic.
  • .bind_tools() — converts our ToolDefinition list into LangChain tool schemas
    and handles function-calling round-trips transparently.
  • Streaming via .astream() — yields AIMessageChunk objects.
  • LangSmith tracing out-of-the-box when LANGCHAIN_API_KEY is set.
"""
from __future__ import annotations

import json
import logging
from typing import Any, AsyncIterator

from langchain_core.messages import (
    AIMessage,
    AIMessageChunk,
    HumanMessage,
    SystemMessage,
    ToolMessage,
    BaseMessage,
)
from langchain_openai import ChatOpenAI

from app.domain.entities.tool import ToolCall, ToolDefinition
from app.domain.ports.llm_port import LLMPort

logger = logging.getLogger(__name__)


# ── Helpers ──────────────────────────────────────────────────────────────────

def _tool_def_to_langchain(td: ToolDefinition) -> dict[str, Any]:
    """Convert our domain ToolDefinition into a LangChain-compatible tool schema."""
    return {
        "type": "function",
        "function": {
            "name": td.name,
            "description": td.description,
            "parameters": td.parameters,
        },
    }


def _dict_to_lc_message(msg: dict[str, Any]) -> BaseMessage:
    """Convert a plain OpenAI-style dict message into a LangChain BaseMessage."""
    role = msg.get("role", "user")
    content = msg.get("content", "")
    if role == "system":
        return SystemMessage(content=content)
    if role == "assistant":
        return AIMessage(content=content)
    if role == "tool":
        return ToolMessage(content=content, tool_call_id=msg.get("tool_call_id", ""))
    # default → human / user
    return HumanMessage(content=content)


# ── Adapter ───────────────────────────────────────────────────────────────────

class LangChainAdapter(LLMPort):
    """
    LLMPort implementation backed by LangChain's ChatOpenAI.

    Drop-in replacement for OpenAIAdapter — selected via LLM_PROVIDER=langchain
    in the .env file (or programmatically in llm_factory.py).
    """

    def __init__(self, api_key: str, model: str, max_tokens: int = 4096) -> None:
        self._model_name = model
        # ChatOpenAI is the LangChain wrapper around the OpenAI chat endpoint.
        # streaming=True enables token-by-token delivery through .astream().
        self._llm = ChatOpenAI(
            api_key=api_key,        # type: ignore[arg-type]
            model=model,
            max_tokens=max_tokens,
            temperature=0.0,
            streaming=True,
        )
        logger.info("LangChainAdapter initialised with model=%s", model)

    def _get_llm(self, temperature: float):
        """
        Return a ChatOpenAI instance with the requested temperature.
        If it matches the cached instance temperature (0.0), reuse it.
        Otherwise create a fresh instance to avoid mutating the cached one.
        LangChain's .bind() only accepts RunnableConfig kwargs (tags, callbacks, etc.)
        — model params like temperature must be set at construction time.
        """
        if temperature == 0.0:
            return self._llm
        return ChatOpenAI(
            api_key=self._llm.openai_api_key,   # type: ignore[arg-type]
            model=self._model_name,
            max_tokens=self._llm.max_tokens,
            temperature=temperature,
            streaming=True,
        )

    # ── Non-streaming ─────────────────────────────────────────────────────────
    async def chat_completion(
        self,
        messages: list[dict[str, Any]],
        tools: list[ToolDefinition] | None = None,
        temperature: float = 0.0,
    ) -> str:
        lc_messages = [_dict_to_lc_message(m) for m in messages]
        llm = self._get_llm(temperature)

        if tools:
            lc_tools = [_tool_def_to_langchain(t) for t in tools]
            llm = llm.bind_tools(lc_tools)  # type: ignore[assignment]

        response: AIMessage = await llm.ainvoke(lc_messages)  # type: ignore[assignment]

        # If the model requested a tool call, serialise it as a sentinel JSON string
        if response.tool_calls:
            tc = response.tool_calls[0]
            return json.dumps(
                {
                    "__tool_call__": True,
                    "tool_name": tc["name"],
                    "arguments": tc["args"],
                    "call_id": tc.get("id", ""),
                }
            )

        return response.content or ""  # type: ignore[return-value]

    # ── Streaming ─────────────────────────────────────────────────────────────
    async def chat_completion_stream(
        self,
        messages: list[dict[str, Any]],
        tools: list[ToolDefinition] | None = None,
        temperature: float = 0.0,
    ) -> AsyncIterator[str]:
        lc_messages = [_dict_to_lc_message(m) for m in messages]
        llm = self._get_llm(temperature)

        if tools:
            lc_tools = [_tool_def_to_langchain(t) for t in tools]
            llm = llm.bind_tools(lc_tools)  # type: ignore[assignment]

        # Accumulate tool-call fragments across streamed chunks
        tool_call_accumulator: dict[int, dict[str, Any]] = {}

        async for chunk in llm.astream(lc_messages):  # type: ignore[union-attr]
            chunk: AIMessageChunk

            # ── Text tokens ───────────────────────────────────────────────
            if chunk.content:
                yield chunk.content  # type: ignore[misc]

            # ── Tool-call fragments ───────────────────────────────────────
            # LangChain delivers tool_call_chunks list on AIMessageChunk
            for tc_chunk in (chunk.tool_call_chunks or []):
                idx = tc_chunk.get("index", 0)
                if idx not in tool_call_accumulator:
                    tool_call_accumulator[idx] = {
                        "id": "",
                        "name": "",
                        "arguments": "",
                    }
                if tc_chunk.get("id"):
                    tool_call_accumulator[idx]["id"] += tc_chunk["id"]
                if tc_chunk.get("name"):
                    tool_call_accumulator[idx]["name"] += tc_chunk["name"]
                if tc_chunk.get("args"):
                    tool_call_accumulator[idx]["arguments"] += tc_chunk["args"]

            # ── Flush completed tool calls when finish_reason triggers ─────
            finish = getattr(chunk, "response_metadata", {}).get("finish_reason")
            if finish in ("tool_calls", "stop") and tool_call_accumulator:
                for tc_data in tool_call_accumulator.values():
                    try:
                        args = json.loads(tc_data["arguments"] or "{}")
                    except json.JSONDecodeError:
                        args = {}
                    yield json.dumps(
                        {
                            "__tool_call__": True,
                            "tool_name": tc_data["name"],
                            "arguments": args,
                            "call_id": tc_data["id"],
                        }
                    )
                tool_call_accumulator = {}

    # ── Parse tool call from sentinel JSON ────────────────────────────────────
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

