"""
FastAPI application factory.
Mounts all routers, registers middleware, and wires lifecycle events.
"""
from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from typing import AsyncGenerator

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.middleware.rate_limit_middleware import RateLimitMiddleware
from app.api.middleware.security_middleware import SecurityMiddleware
from app.api.v1.routers.agent_router import router as agent_router
from app.api.v1.routers.health_router import router as health_router
from app.config.settings import get_settings
from app.infrastructure.db.mysql_client import close_db, init_db  # backed by SQL Server via aioodbc

# Configuración de logging profesional
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)-8s | %(name)s — %(message)s",
)
logger = logging.getLogger(__name__)


def create_app() -> FastAPI:
    settings = get_settings()

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
        """
        Maneja el ciclo de vida de la aplicación:
        Inicio de conexiones y limpieza al apagar.
        """
        logger.info("Starting %s v%s", settings.APP_NAME, settings.APP_VERSION)
        logger.info("LLM provider: %s", settings.LLM_PROVIDER)
        # Diagnostic logs (masked keys)
        openai_mask = (settings.OPENAI_API_KEY[:4] + '...' ) if settings.OPENAI_API_KEY else None
        anthropic_mask = (settings.ANTHROPIC_API_KEY[:4] + '...' ) if settings.ANTHROPIC_API_KEY else None
        logger.info("OPENAI_API_KEY present: %s, masked=%s", bool(settings.OPENAI_API_KEY), openai_mask)
        logger.info("ANTHROPIC_API_KEY present: %s, masked=%s", bool(settings.ANTHROPIC_API_KEY), anthropic_mask)

        try:
            init_db(settings)
            logger.info("Database pool successfully initialised")

            yield

        except Exception as e:
            logger.error("Error during startup: %s", e)
            raise e
        finally:
            await close_db()
            logger.info("Database pool closed safely")

    app = FastAPI(
        title=settings.APP_NAME,
        version=settings.APP_VERSION,
        description=(
            "ReAct Agent with Hexagonal Architecture.\n\n"
            "Uses streaming SSE and tool-calling to reason over ERP data and regulations."
        ),
        docs_url="/docs",
        redoc_url="/redoc",
        lifespan=lifespan,
    )

    # ── MIDDLEWARES (Orden de ejecución: de abajo hacia arriba) ─────────────

    # 3. CORS (Ejecutado al final, antes de llegar al router)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.CORS_ORIGINS if hasattr(settings, 'CORS_ORIGINS') else ["*"],
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # 2. Seguridad (Validación de API Key e inyecciones)
    app.add_middleware(
        SecurityMiddleware,
        valid_api_keys=settings.VALID_API_KEYS,
        api_key_header=settings.API_KEY_HEADER,
    )

    # 1. Rate Limiting (Ejecutado PRIMERO para descartar tráfico abusivo pronto)
    app.add_middleware(
        RateLimitMiddleware,
        max_requests=settings.RATE_LIMIT_REQUESTS,
        window_seconds=settings.RATE_LIMIT_WINDOW_SECONDS,
        api_key_header=settings.API_KEY_HEADER,
    )

    # ── ROUTERS ─────────────────────────────────────────────────────────────

    # Health check fuera del prefijo de API usualmente es mejor para balanceadores
    app.include_router(health_router, tags=["System"])

    # Rutas de negocio con prefijo (ej: /api/v1)
    app.include_router(
        agent_router,
        prefix=settings.API_PREFIX,
        tags=["Agent"]
    )

    return app


# Instancia global para ser consumida por Uvicorn/Gunicorn
app = create_app()

if __name__ == "__main__":
    import uvicorn

    _settings = get_settings()
    uvicorn.run(
        "app.main:app",
        host="0.0.0.0",
        port=8000,
        reload=True,
        log_level="info",
    )
