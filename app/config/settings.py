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

    # ── Database (SQL Server — local Docker & Azure SQL) ─────────────────────
    # Local dev (docker-compose): MSSQL_HOST=db, MSSQL_PORT=1433
    # Azure prod: MSSQL_HOST=<azure-sql-fqdn>, driver handled via ODBC DSN
    MSSQL_HOST: str = "db"
    MSSQL_PORT: int = 1433
    MSSQL_USER: str = "sa"
    MSSQL_PASSWORD: str = "React4as2#Strong!"
    MSSQL_DATABASE: str = "react_db"
    # ODBC driver name — must match the driver installed in the container/host
    # Local Docker: "ODBC Driver 18 for SQL Server"
    # Azure: same or "ODBC Driver 17 for SQL Server"
    MSSQL_DRIVER: str = "ODBC Driver 18 for SQL Server"

    @property
    def DATABASE_URL(self) -> str:  # noqa: N802
        # aioodbc connection string (async ODBC via SQLAlchemy)
        # TrustServerCertificate=yes is needed for local dev with self-signed cert
        conn = (
            f"DRIVER={{{self.MSSQL_DRIVER}}};"
            f"SERVER={self.MSSQL_HOST},{self.MSSQL_PORT};"
            f"DATABASE={self.MSSQL_DATABASE};"
            f"UID={self.MSSQL_USER};"
            f"PWD={self.MSSQL_PASSWORD};"
            "TrustServerCertificate=yes;"
            "Encrypt=yes;"
        )
        return f"mssql+aioodbc:///?odbc_connect={conn}"

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
