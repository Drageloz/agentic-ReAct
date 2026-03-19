"""Domain Port for ERP data access."""
from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any


class ERPPort(ABC):
    """
    Abstract port for ERP data queries.
    Concrete adapters implement against MySQL (or any other DB).
    """

    @abstractmethod
    async def get_shipment(self, shipment_id: str) -> dict[str, Any] | None:
        """Fetch a single shipment record by ID."""

    @abstractmethod
    async def list_shipments(
        self,
        user_id: str | None = None,
        status: str | None = None,
        limit: int = 20,
    ) -> list[dict[str, Any]]:
        """List shipments with optional filters."""

    @abstractmethod
    async def get_user_profile(self, user_id: str) -> dict[str, Any] | None:
        """
        Fetch non-sensitive user profile data.
        NOTE: salary and other PII fields MUST be excluded at the adapter level.
        """

