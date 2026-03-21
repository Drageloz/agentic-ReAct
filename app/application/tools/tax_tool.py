"""
Tax Discrepancy Tool — pure Python business logic (no external dependencies).

Simulates the tax validation layer that a logistics ERP would perform:
  - Applies region-specific VAT / tax rates.
  - Compares declared amount against the expected tax calculation.
  - Returns the discrepancy (positive = under-declared, negative = over-declared).

This tool is intentionally stateless so it can be called multiple times within
a single ReAct iteration chain without side effects.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

# ── Regional tax configuration (mock ERP configuration table) ────────────────
# Rates represent the standard VAT / goods-and-services tax for each region.
# In production these would come from the ERP's tax configuration tables.
_TAX_RATES: dict[str, float] = {
    # European Union
    "ES": 0.21,   # Spain
    "FR": 0.20,   # France
    "DE": 0.19,   # Germany
    "IT": 0.22,   # Italy
    "PT": 0.23,   # Portugal
    "NL": 0.21,   # Netherlands
    "BE": 0.21,   # Belgium
    "AT": 0.20,   # Austria
    "PL": 0.23,   # Poland
    "SE": 0.25,   # Sweden
    "DK": 0.25,   # Denmark
    "FI": 0.24,   # Finland
    "CZ": 0.21,   # Czech Republic
    "IE": 0.23,   # Ireland
    "CH": 0.081,  # Switzerland (non-EU)
    # UK
    "UK": 0.20,
    "GB": 0.20,
    # North America
    "US": 0.085,  # US average sales tax (varies by state)
    "CA": 0.13,   # Canada HST average
    "MX": 0.16,   # Mexico IVA
    # LATAM
    "BR": 0.17,   # Brazil ICMS average
    "AR": 0.21,   # Argentina IVA
    "CO": 0.19,   # Colombia IVA
    "CL": 0.19,   # Chile IVA
    # Asia-Pacific
    "AU": 0.10,   # Australia GST
    "NZ": 0.15,   # New Zealand GST
    "JP": 0.10,   # Japan consumption tax
    "SG": 0.09,   # Singapore GST
    "CN": 0.13,   # China VAT standard rate
    "IN": 0.18,   # India GST standard rate
    # Middle East
    "AE": 0.05,   # UAE VAT
    "SA": 0.15,   # Saudi Arabia VAT
    "NO": 0.25,   # Norway MVA
}

_DEFAULT_RATE = 0.20  # fallback when region is unknown
_DISCREPANCY_THRESHOLD = 0.01  # 1 cent tolerance to avoid float noise


@dataclass
class TaxDiscrepancyResult:
    """Structured result returned by calculate_tax_discrepancy."""
    region: str
    base_amount: float
    declared_tax: float
    expected_tax: float
    discrepancy: float          # declared_tax - expected_tax
    discrepancy_pct: float      # discrepancy / expected_tax  (signed)
    tax_rate_applied: float
    status: str                 # "OK" | "UNDER_DECLARED" | "OVER_DECLARED"
    alert: bool
    message: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "region": self.region,
            "base_amount": self.base_amount,
            "declared_tax": self.declared_tax,
            "expected_tax": self.expected_tax,
            "discrepancy": self.discrepancy,
            "discrepancy_pct": round(self.discrepancy_pct * 100, 4),
            "tax_rate_applied": self.tax_rate_applied,
            "status": self.status,
            "alert": self.alert,
            "message": self.message,
        }


def calculate_tax_discrepancy(
    amount: float,
    region: str,
    declared_tax: float | None = None,
) -> dict[str, Any]:
    """
    Calculate the expected tax for *amount* in *region* and, if *declared_tax*
    is provided, compute the discrepancy against what was actually declared.

    Args:
        amount:       The pre-tax base amount (e.g. invoice value in EUR/USD).
        region:       ISO-3166 alpha-2 country / region code (e.g. "ES", "DE").
        declared_tax: The tax amount the counterpart declared. If None, only
                      the expected tax is computed (no discrepancy check).

    Returns:
        A dict with keys: region, base_amount, declared_tax, expected_tax,
        discrepancy, discrepancy_pct, tax_rate_applied, status, alert, message.
    """
    region_upper = region.strip().upper()
    rate = _TAX_RATES.get(region_upper, _DEFAULT_RATE)
    expected = round(amount * rate, 2)

    # If no declared_tax is provided, assume it matches the expected value
    if declared_tax is None:
        declared_tax = expected

    discrepancy = round(declared_tax - expected, 2)
    discrepancy_pct = (discrepancy / expected) if expected != 0 else 0.0
    alert = abs(discrepancy) > _DISCREPANCY_THRESHOLD

    if not alert:
        status = "OK"
        message = (
            f"Tax calculation for region {region_upper} is correct. "
            f"Expected {expected} at {rate*100:.1f}% — declared {declared_tax}."
        )
    elif discrepancy < 0:
        status = "UNDER_DECLARED"
        message = (
            f"⚠️  UNDER-DECLARED TAX in {region_upper}: "
            f"declared {declared_tax} but expected {expected} "
            f"({rate*100:.1f}% on {amount}). "
            f"Shortfall: {abs(discrepancy)} ({abs(discrepancy_pct)*100:.2f}%)."
        )
    else:
        status = "OVER_DECLARED"
        message = (
            f"ℹ️  OVER-DECLARED TAX in {region_upper}: "
            f"declared {declared_tax} but expected {expected} "
            f"({rate*100:.1f}% on {amount}). "
            f"Excess: {discrepancy} ({discrepancy_pct*100:.2f}%)."
        )

    return TaxDiscrepancyResult(
        region=region_upper,
        base_amount=amount,
        declared_tax=declared_tax,
        expected_tax=expected,
        discrepancy=discrepancy,
        discrepancy_pct=round(discrepancy_pct, 6),
        tax_rate_applied=rate,
        status=status,
        alert=alert,
        message=message,
    ).to_dict()

