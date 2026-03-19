"""
Dependency Injection wiring.
Maps domain ports to infrastructure adapters.
All FastAPI Depends() calls resolve here — domain/application layers stay pure.
"""
from __future__ import annotations

from functools import lru_cache

from app.application.services.react_orchestrator import ReactOrchestrator
from app.application.tools.tool_registry import ToolRegistry
from app.application.use_cases.get_history import GetConversationHistoryUseCase
from app.application.use_cases.run_agent import RunAgentUseCase
from app.config.settings import Settings, get_settings
from app.infrastructure.db.mysql_client import get_session_factory
from app.infrastructure.db.mysql_conversation_adapter import MySQLConversationAdapter
from app.infrastructure.db.mysql_erp_adapter import MySQLERPAdapter
from app.infrastructure.llm.llm_factory import create_llm_adapter
from app.infrastructure.rag.simulated_rag_adapter import SimulatedRAGAdapter


# ── Singletons (created once at startup) ─────────────────────────────────────

@lru_cache
def _get_erp_adapter() -> MySQLERPAdapter:
    return MySQLERPAdapter(get_session_factory())


@lru_cache
def _get_conversation_adapter() -> MySQLConversationAdapter:
    return MySQLConversationAdapter(get_session_factory())


@lru_cache
def _get_rag_adapter() -> SimulatedRAGAdapter:
    return SimulatedRAGAdapter()


@lru_cache
def _get_tool_registry() -> ToolRegistry:
    return ToolRegistry(erp_port=_get_erp_adapter(), rag_port=_get_rag_adapter())


@lru_cache
def _get_llm_adapter():
    """Create and cache the LLM adapter. This function must not accept a Settings
    instance as an argument because `Settings` is unhashable and would break
    functools.lru_cache (which requires hashable args).
    """
    s = get_settings()
    return create_llm_adapter(s)


@lru_cache
def _get_orchestrator() -> ReactOrchestrator:
    settings = get_settings()
    return ReactOrchestrator(
        llm=_get_llm_adapter(),
        tool_registry=_get_tool_registry(),
    )


# ── FastAPI Depends() factories ───────────────────────────────────────────────

def get_run_agent_use_case() -> RunAgentUseCase:
    settings = get_settings()
    return RunAgentUseCase(
        orchestrator=_get_orchestrator(),
        conversation_repo=_get_conversation_adapter(),
        max_iterations=settings.AGENT_MAX_ITERATIONS,
    )


def get_history_use_case() -> GetConversationHistoryUseCase:
    return GetConversationHistoryUseCase(repo=_get_conversation_adapter())
