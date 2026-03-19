"""
MySQL ERP Adapter — implements ERPPort.
Queries the `shipments` and `users` tables.

SECURITY NOTE: salary and other sensitive columns are NEVER returned.
"""
from __future__ import annotations

import logging
from typing import Any

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.domain.ports.erp_port import ERPPort

logger = logging.getLogger(__name__)

# Columns that are explicitly BLOCKED from being exposed to the agent
_SENSITIVE_COLUMNS = frozenset({"salary", "password", "password_hash", "ssn", "credit_card"})


def _sanitize_row(row_dict: dict[str, Any]) -> dict[str, Any]:
    return {k: v for k, v in row_dict.items() if k.lower() not in _SENSITIVE_COLUMNS}


class MySQLERPAdapter(ERPPort):
    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        self._session_factory = session_factory

    async def get_shipment(self, shipment_id: str) -> dict[str, Any] | None:
        async with self._session_factory() as session:
            result = await session.execute(
                text(
                    """
                    SELECT id, tracking_number, status, origin, destination,
                           estimated_delivery, weight_kg, carrier, user_id, created_at
                    FROM shipments
                    WHERE id = :shipment_id
                    LIMIT 1
                    """
                ),
                {"shipment_id": shipment_id},
            )
            row = result.mappings().first()
            if row is None:
                return None
            return _sanitize_row(dict(row))

    async def list_shipments(
        self,
        user_id: str | None = None,
        status: str | None = None,
        limit: int = 20,
    ) -> list[dict[str, Any]]:
        conditions = []
        params: dict[str, Any] = {"limit": limit}

        if user_id:
            conditions.append("user_id = :user_id")
            params["user_id"] = user_id
        if status:
            conditions.append("status = :status")
            params["status"] = status

        where_clause = ("WHERE " + " AND ".join(conditions)) if conditions else ""

        async with self._session_factory() as session:
            result = await session.execute(
                text(
                    f"""
                    SELECT id, tracking_number, status, origin, destination,
                           estimated_delivery, weight_kg, carrier, user_id, created_at
                    FROM shipments
                    {where_clause}
                    ORDER BY created_at DESC
                    LIMIT :limit
                    """
                ),
                params,
            )
            rows = result.mappings().all()
            return [_sanitize_row(dict(r)) for r in rows]

    async def get_user_profile(self, user_id: str) -> dict[str, Any] | None:
        async with self._session_factory() as session:
            result = await session.execute(
                text(
                    """
                    SELECT id, username, email, full_name, department, role, created_at
                    FROM users
                    WHERE id = :user_id
                    LIMIT 1
                    """
                ),
                {"user_id": user_id},
            )
            row = result.mappings().first()
            if row is None:
                return None
            # Extra safety: strip sensitive columns even though they're not in SELECT
            return _sanitize_row(dict(row))

