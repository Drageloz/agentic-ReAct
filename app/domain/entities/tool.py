"""
Domain Entities: Tool definitions used by the ReAct agent.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Optional
from uuid import UUID, uuid4


@dataclass
class ToolDefinition:
    """Static description of a tool — sent to the LLM as function spec."""
    name: str
    description: str
    parameters: dict[str, Any]  # JSON Schema object


@dataclass
class ToolCall:
    """A concrete invocation request produced by the LLM."""
    tool_name: str
    arguments: dict[str, Any]
    call_id: UUID = field(default_factory=uuid4)


@dataclass
class ToolResult:
    """The result returned by executing a tool."""
    call_id: UUID
    tool_name: str
    result: Any
    is_error: bool = False
    error_message: Optional[str] = None

    def to_observation_text(self) -> str:
        if self.is_error:
            return f"[ERROR from {self.tool_name}]: {self.error_message}"
        return f"[Result from {self.tool_name}]: {self.result}"

