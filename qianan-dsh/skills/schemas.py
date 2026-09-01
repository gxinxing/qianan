"""千岸 DSH Skills 共享数据模型。"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class ComplianceIssue:
    check_id: str
    severity: str       # "error" | "warn"
    field: str
    message: str


@dataclass
class EconomicsInput:
    cost_cny: float
    weight_kg: float
    length_cm: float
    width_cm: float
    height_cm: float
    target_margin: float = 0.15
    first_mile: str = "sea"
    turnover_months: float = 2.0
    fixed_cost_cny: float = 0.0
    market_price_min: float | None = None
    market_price_max: float | None = None


@dataclass
class PlatformEconomics:
    platform: str
    display_name: str
    purchase: float = 0.0
    first_mile: float = 0.0
    last_mile: float = 0.0
    storage: float = 0.0
    return_loss: float = 0.0
    commission: float = 0.0
    ad: float = 0.0
    vat: float = 0.0
    profit: float = 0.0
    margin: float = 0.0
    break_even_price: float = 0.0
    suggested_price: float = 0.0
    bep_units: int | None = None
    verdict: str = "green"
    verdict_reason: str = ""


@dataclass
class EconomicsResult:
    chargeable_weight_kg: float
    volume_weight_kg: float
    fx_usd_cny: float
    fx_source: str = "builtin"
    platforms: list[PlatformEconomics] = field(default_factory=list)
