"""
Tool Registry — maps tool names to their domain definitions and async handlers.
This is the ONLY place in the application that knows which tools exist.
"""
from __future__ import annotations

import logging
from typing import Any, Callable, Coroutine

from app.domain.entities.tool import ToolDefinition, ToolResult, ToolCall
from app.domain.ports.erp_port import ERPPort
from app.domain.ports.rag_port import RAGPort
from app.application.tools.tax_tool import calculate_tax_discrepancy

logger = logging.getLogger(__name__)

ToolHandler = Callable[[dict[str, Any]], Coroutine[Any, Any, Any]]


# ── Tool definitions (JSON Schema for LLM function calling) ──────────────────

GET_ERP_DATA_DEFINITION = ToolDefinition(
    name="get_erp_data",
    description=(
        "Query the ERP system for logistics and shipment data. "
        "Can retrieve shipment details by ID, list shipments with optional filters "
        "(user_id, status), or fetch a user profile (non-sensitive fields only)."
    ),
    parameters={
        "type": "object",
        "properties": {
            "action": {
                "type": "string",
                "enum": ["get_shipment", "list_shipments", "get_user_profile"],
                "description": "The specific ERP operation to perform.",
            },
            "shipment_id": {
                "type": ["string", "null"],
                "description": "Shipment ID — required for action=get_shipment. Pass null otherwise.",
            },
            "user_id": {
                "type": ["string", "null"],
                "description": "User ID — used in list_shipments filter or get_user_profile. Pass null if not needed.",
            },
            "status": {
                "type": ["string", "null"],
                "description": "Filter shipments by status (e.g. 'in_transit', 'delivered'). Pass null for no filter.",
            },
            "limit": {
                "type": ["integer", "null"],
                "description": "Max number of records to return. Pass null to use default (20).",
            },
        },
        # All keys must be in `required` for OpenAI strict mode.
        # Optional ones use ["type", "null"] so the model can pass null.
        "required": ["action", "shipment_id", "user_id", "status", "limit"],
        "additionalProperties": False,
    },
)

SEARCH_REGULATIONS_DEFINITION = ToolDefinition(
    name="search_regulations",
    description=(
        "Search the regulatory knowledge base for compliance rules, "
        "shipping regulations, customs requirements, and policy documents."
    ),
    parameters={
        "type": "object",
        "properties": {
            "query": {
                "type": "string",
                "description": "Natural language search query.",
            },
            "top_k": {
                "type": ["integer", "null"],
                "description": "Number of documents to retrieve. Pass null to use default (3).",
            },
        },
        "required": ["query", "top_k"],
        "additionalProperties": False,
    },
)

CALCULATE_TAX_DISCREPANCY_DEFINITION = ToolDefinition(
    name="calculate_tax_discrepancy",
    description=(
        "Calculate the expected tax for a given base amount and region, "
        "and detect discrepancies against a declared tax amount. "
        "Use this to validate invoice taxes, detect under/over-declarations, "
        "and support audit workflows. Returns expected tax, discrepancy amount, "
        "percentage deviation, and an alert flag."
    ),
    parameters={
        "type": "object",
        "properties": {
            "amount": {
                "type": "number",
                "description": "Pre-tax base amount (e.g. invoice value in EUR/USD).",
            },
            "region": {
                "type": "string",
                "description": (
                    "ISO-3166 alpha-2 country/region code (e.g. 'ES', 'DE', 'US'). "
                    "Determines the applicable tax rate."
                ),
            },
            "declared_tax": {
                "type": ["number", "null"],
                "description": (
                    "The tax amount declared by the counterpart. "
                    "Pass null if not available — only the expected tax will be calculated."
                ),
            },
        },
        "required": ["amount", "region", "declared_tax"],
        "additionalProperties": False,
    },
)

ALL_TOOL_DEFINITIONS: list[ToolDefinition] = [
    GET_ERP_DATA_DEFINITION,
    SEARCH_REGULATIONS_DEFINITION,
    CALCULATE_TAX_DISCREPANCY_DEFINITION,
]


# ── Registry class ────────────────────────────────────────────────────────────

class ToolRegistry:
    """Dispatches ToolCall requests to the correct port/handler."""

    def __init__(self, erp_port: ERPPort, rag_port: RAGPort) -> None:
        self._erp = erp_port
        self._rag = rag_port

    def get_definitions(self) -> list[ToolDefinition]:
        return ALL_TOOL_DEFINITIONS

    async def execute(self, tool_call: ToolCall) -> ToolResult:
        try:
            if tool_call.tool_name == "get_erp_data":
                result = await self._handle_erp(tool_call.arguments)
            elif tool_call.tool_name == "search_regulations":
                result = await self._handle_rag(tool_call.arguments)
            elif tool_call.tool_name == "calculate_tax_discrepancy":
                result = self._handle_tax(tool_call.arguments)
            else:
                return ToolResult(
                    call_id=tool_call.call_id,
                    tool_name=tool_call.tool_name,
                    result=None,
                    is_error=True,
                    error_message=f"Unknown tool: {tool_call.tool_name}",
                )
            return ToolResult(
                call_id=tool_call.call_id,
                tool_name=tool_call.tool_name,
                result=result,
            )
        except Exception as exc:
            logger.exception("Tool execution error for %s", tool_call.tool_name)
            return ToolResult(
                call_id=tool_call.call_id,
                tool_name=tool_call.tool_name,
                result=None,
                is_error=True,
                error_message=str(exc),
            )

    async def _handle_erp(self, args: dict[str, Any]) -> Any:
        action = args.get("action")
        if action == "get_shipment":
            return await self._erp.get_shipment(args["shipment_id"])
        if action == "list_shipments":
            # null values sent by the LLM (strict mode) → treat as None/default
            limit_raw = args.get("limit")
            return await self._erp.list_shipments(
                user_id=args.get("user_id") or None,
                status=args.get("status") or None,
                limit=int(limit_raw) if limit_raw is not None else 20,
            )
        if action == "get_user_profile":
            return await self._erp.get_user_profile(args["user_id"])
        raise ValueError(f"Unknown ERP action: {action}")

    async def _handle_rag(self, args: dict[str, Any]) -> Any:
        top_k_raw = args.get("top_k")
        docs = await self._rag.search(
            query=args["query"],
            top_k=int(top_k_raw) if top_k_raw is not None else 3,
        )
        return [
            {
                "doc_id": d.doc_id,
                "title": d.title,
                "content": d.content[:800],  # Truncate for LLM context window
                "score": d.score,
                "source": d.source,
            }
            for d in docs
        ]

    def _handle_tax(self, args: dict[str, Any]) -> Any:
        """Synchronous handler — calculate_tax_discrepancy is pure Python."""
        return calculate_tax_discrepancy(
            amount=float(args["amount"]),
            region=str(args["region"]),
            declared_tax=float(args["declared_tax"]) if args.get("declared_tax") is not None else None,
        )

