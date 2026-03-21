"""
Application Settings — loaded from environment variables via Pydantic BaseSettings.
"""
from __future__ import annotations

from enum import Enum
from functools import lru_cache
from typing import Optional
from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings


class LLMProvider(str, Enum):
    OPENAI = "openai"
    CLAUDE = "claude"
    LANGCHAIN = "langchain"   # LangChain adapter (uses ChatOpenAI under the hood)


class RAGProvider(str, Enum):
    SIMULATED = "simulated"   # keyword TF-IDF — no external services needed
    CHROMA = "chroma"         # ChromaDB + OpenAI Embeddings — real vector store


class Settings(BaseSettings):
    # ── Application ──────────────────────────────────────────────────────────
    APP_NAME: str = "agentic-ReAct"
    APP_VERSION: str = "1.0.0"
    DEBUG: bool = False
    API_PREFIX: str = "/api/v1"

    # ── LLM Provider ─────────────────────────────────────────────────────────
    LLM_PROVIDER: LLMProvider = LLMProvider.OPENAI
    OPENAI_API_KEY: Optional[str] = None
    OPENAI_MODEL: str = "gpt-4o"
    ANTHROPIC_API_KEY: Optional[str] = None
    ANTHROPIC_MODEL: str = "claude-3-5-sonnet-20241022"
    LLM_TEMPERATURE: float = 0.0
    LLM_MAX_TOKENS: int = 4096

    # ── ReAct Agent ──────────────────────────────────────────────────────────
    AGENT_MAX_ITERATIONS: int = 10

    # ── RAG Provider ─────────────────────────────────────────────────────────
    # simulated → keyword TF-IDF (no API key needed, default for local dev)
    # chroma    → ChromaDB + OpenAI Embeddings (real vector store with metadata filtering)
    RAG_PROVIDER: RAGProvider = RAGProvider.CHROMA

    # ── Database (MySQL) ─────────────────────────────────────────────────────
    MYSQL_HOST: str = "db"
    MYSQL_PORT: int = 3306
    MYSQL_USER: str = "reactuser"
    MYSQL_PASSWORD: str = "reactpass"
    MYSQL_DATABASE: str = "react_db"

    @property
    def DATABASE_URL(self) -> str:  # noqa: N802
        return (
            f"mysql+aiomysql://{self.MYSQL_USER}:{self.MYSQL_PASSWORD}"
            f"@{self.MYSQL_HOST}:{self.MYSQL_PORT}/{self.MYSQL_DATABASE}"
        )

    # ── Security ─────────────────────────────────────────────────────────────
    SECRET_KEY: str = "change-me-in-production-please"
    API_KEY_HEADER: str = "X-API-Key"
    VALID_API_KEYS: list[str] = Field(default=["dev-key-12345"])

    # ── Rate limiting (in-memory) ─────────────────────────────────────────────
    RATE_LIMIT_REQUESTS: int = 20
    RATE_LIMIT_WINDOW_SECONDS: int = 60

    # Use an absolute path to the .env file located in the project root so the
    # environment file is discovered regardless of the current working directory
    # (useful when running from PyCharm/uvicorn with different cwd).
    _env_path: Path = Path(__file__).resolve().parents[2] / ".env"
    model_config = {
        "env_file": str(_env_path),
        "env_file_encoding": "utf-8",
        "extra": "ignore",
    }


@lru_cache
def get_settings() -> Settings:
    return Settings()
