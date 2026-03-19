"""
Domain Entities: Agent State and ReAct Steps.
Pure domain objects — no framework dependencies.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Optional
from uuid import UUID, uuid4


class StepType(str, Enum):
    THOUGHT = "thought"
    ACTION = "action"
    OBSERVATION = "observation"
    FINAL_ANSWER = "final_answer"
    ERROR = "error"


@dataclass
class ReActStep:
    """Represents a single step in the ReAct reasoning loop."""
    step_type: StepType
    content: str
    tool_name: Optional[str] = None
    tool_input: Optional[dict[str, Any]] = None
    step_id: UUID = field(default_factory=uuid4)

    def to_dict(self) -> dict[str, Any]:
        return {
            "step_id": str(self.step_id),
            "step_type": self.step_type.value,
            "content": self.content,
            "tool_name": self.tool_name,
            "tool_input": self.tool_input,
        }


@dataclass
class AgentState:
    """
    Holds the full state of a running ReAct agent instance.
    Immutable between iterations — each loop creates a new snapshot.
    """
    session_id: UUID
    user_id: str
    original_query: str
    steps: list[ReActStep] = field(default_factory=list)
    final_answer: Optional[str] = None
    max_iterations: int = 10
    current_iteration: int = 0

    @property
    def is_done(self) -> bool:
        return self.final_answer is not None or self.current_iteration >= self.max_iterations

    def add_step(self, step: ReActStep) -> None:
        self.steps.append(step)
        if step.step_type == StepType.FINAL_ANSWER:
            self.final_answer = step.content

    def increment_iteration(self) -> None:
        self.current_iteration += 1

    def build_history_text(self) -> str:
        """Serialise previous steps as context for the next LLM call."""
        lines: list[str] = []
        for s in self.steps:
            if s.step_type == StepType.THOUGHT:
                lines.append(f"Thought: {s.content}")
            elif s.step_type == StepType.ACTION:
                lines.append(f"Action: {s.tool_name}({s.tool_input})")
            elif s.step_type == StepType.OBSERVATION:
                lines.append(f"Observation: {s.content}")
        return "\n".join(lines)

