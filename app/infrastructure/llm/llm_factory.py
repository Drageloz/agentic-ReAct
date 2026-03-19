"""
LLM Factory — selects and instantiates the correct LLMPort adapter
based on the LLM_PROVIDER environment variable.
"""
from __future__ import annotations

from app.config.settings import LLMProvider, Settings
from app.domain.ports.llm_port import LLMPort


def create_llm_adapter(settings: Settings) -> LLMPort:
    """
    Factory function.  Returns a concrete LLMPort implementation.
    Add new providers here without touching domain or application code.
    """
    if settings.LLM_PROVIDER == LLMProvider.OPENAI:
        from app.infrastructure.llm.openai_adapter import OpenAIAdapter

        if not settings.OPENAI_API_KEY:
            raise ValueError("OPENAI_API_KEY is required when LLM_PROVIDER=openai")
        return OpenAIAdapter(
            api_key=settings.OPENAI_API_KEY,
            model=settings.OPENAI_MODEL,
            max_tokens=settings.LLM_MAX_TOKENS,
        )

    if settings.LLM_PROVIDER == LLMProvider.CLAUDE:
        from app.infrastructure.llm.claude_adapter import ClaudeAdapter

        if not settings.ANTHROPIC_API_KEY:
            raise ValueError("ANTHROPIC_API_KEY is required when LLM_PROVIDER=claude")
        return ClaudeAdapter(
            api_key=settings.ANTHROPIC_API_KEY,
            model=settings.ANTHROPIC_MODEL,
            max_tokens=settings.LLM_MAX_TOKENS,
        )

    raise ValueError(f"Unsupported LLM_PROVIDER: {settings.LLM_PROVIDER}")

