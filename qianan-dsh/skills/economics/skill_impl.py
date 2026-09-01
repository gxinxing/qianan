"""单位经济测算 Skill 实现 — 纯确定性数学，无 LLM 调用。

输入卖家侧事实 → 输出 5 平台保本价/建议价/净利/盈亏判定。
费率来源：data/rules/{platform}.json → economics 块。
汇率由调用方注入（fx-live skill），否则回退内置 7.2。
"""
from __future__ import annotations

import logging
from typing import Any

from .. import all_platforms
from ..schemas import EconomicsInput, EconomicsResult, PlatformEconomics

logger = logging.getLogger(__name__)

FIRST_MILE_CNY_PER_KG = {"sea": 8.0, "air": 28.0}
SALVAGE_RATIO = 0.5
MIN_DENOM = 0.05


def _evaluate_platform(
    platform: str, rules: dict, inp: EconomicsInput, fx: float = 7.2
) -> PlatformEconomics:
    """计算单平台单位经济。"""
    eco = rules.get("economics", {})
    length_m = inp.length_cm / 100
    width_m = inp.width_cm / 100
    height_m = inp.height_cm / 100
    volume_weight = length_m * width_m * height_m * 1000  # kg (L×W×H/6000)
    chargeable = max(inp.weight_kg, volume_weight)

    purchase = inp.cost_cny / fx
    first_mile = chargeable * FIRST_MILE_CNY_PER_KG[inp.first_mile] / fx
    volume_m3 = length_m * width_m * height_m
    storage = volume_m3 * float(eco.get("fulfillment", {}).get("monthlyStoragePerCubicMeter", 27.01)) * inp.turnover_months
    last_mile = _last_mile(eco, chargeable)

    commission_rate = float(eco.get("commissionRate", 0.15))
    return_rate = float(eco.get("returnRateDefault", 0.05))
    handling = float(eco.get("returnHandlingFee", 1.0))
    vat = float(eco.get("vatRate", 0.0))

    return_loss = return_rate * (handling + SALVAGE_RATIO * (purchase + first_mile))
    cash_cost = purchase + first_mile + last_mile + storage + return_loss

    denom = 1 - commission_rate - inp.target_margin
    if denom <= MIN_DENOM:
        suggested = cash_cost * 1.5
    else:
        suggested = cash_cost / denom
    break_even = cash_cost / max(1 - commission_rate, 0.05)
    suggested = suggested * (1 + vat)
    break_even = break_even * (1 + vat)

    net_revenue = suggested / (1 + vat)
    commission_amt = net_revenue * commission_rate
    profit = net_revenue * (1 - commission_rate) - cash_cost
    margin = profit / net_revenue if net_revenue > 0 else 0.0

    fixed_usd = inp.fixed_cost_cny / fx
    bep_units = int(fixed_usd / max(profit, 0.01)) if profit > 0 and fixed_usd > 0 else None

    display_name = rules.get("displayName", platform)

    # Verdict logic
    verdict, verdict_reason = _verdict(
        platform, break_even, suggested, margin,
        inp.market_price_min, inp.market_price_max,
        commission_rate, cash_cost
    )

    return PlatformEconomics(
        platform=platform,
        display_name=display_name,
        purchase=round(purchase, 2),
        first_mile=round(first_mile, 2),
        last_mile=round(last_mile, 2),
        storage=round(storage, 2),
        return_loss=round(return_loss, 2),
        commission=round(commission_amt, 2),
        ad=round(net_revenue * float(eco.get("adTacosDefault", 0.15)), 2),
        vat=round(suggested - net_revenue, 2),
        profit=round(profit, 2),
        margin=round(margin, 4),
        break_even_price=round(break_even, 2),
        suggested_price=round(suggested, 2),
        bep_units=bep_units,
        verdict=verdict,
        verdict_reason=verdict_reason,
    )


def _last_mile(eco: dict, chargeable_kg: float) -> float:
    """尾程费用（FBA 阶梯 or 标准 flat fee）。"""
    ful = eco.get("fulfillment", {})
    if ful.get("type") == "fba_tiers":
        tiers = ful.get("tiers", [])
        for tier in tiers:
            if chargeable_kg <= float(tier["maxKg"]):
                return float(tier["fee"])
        top = tiers[-1]
        return float(top["fee"]) + (chargeable_kg - float(top["maxKg"])) * 1.2
    return float(ful.get("fee", 1.2))


def _verdict(
    platform: str, break_even: float, suggested: float, margin: float,
    price_min, price_max, commission_rate: float, cash_cost: float
) -> tuple[str, str]:
    """判定绿/黄/红。"""
    if price_min is not None and price_max is not None:
        if break_even > price_max:
            return ("red", f"保本价 ${break_even:.2f} 高于市场带最高 ${price_max:.2f}——成本倒挂，建议放弃")
        mid = (price_min + price_max) / 2
        net_mid = mid * (1 - commission_rate)
        profit_mid = net_mid - cash_cost
        if profit_mid <= 0:
            return ("red", f"按市场带中位价 ${mid:.2f} 销售仍亏损")
        if suggested > price_max:
            return ("yellow", f"建议价 ${suggested:.2f} 高于市场带，需品牌溢价或降价")
        return ("green", f"建议价落在市场带内，净利率 {margin * 100:.1f}%")
    return ("green", f"保本价 ${break_even:.2f}，建议价 ${suggested:.2f}")


class EconomicsSkill:
    """5 平台单位经济测算（确定性引擎，不调用 LLM）。"""

    def __init__(self, config: dict | None = None, mock: bool | None = None) -> None:
        self.config = config or {}
        if mock is not None:
            self.config["mock"] = mock
        self.mock_mode = self.config.get("mock", False)

    async def run(self, **kwargs: Any) -> dict[str, Any]:
        """主入口：计算单位经济。

        参数通过 EconomicsInput 校验，fx 默认 7.2。
        """
        inp = EconomicsInput(**kwargs)
        fx = float(self.config.get("fx", 7.2))
        fx_source = self.config.get("fx_source", "builtin")

        platforms_data = all_platforms()
        results = [
            _evaluate_platform(p, rules, inp, fx)
            for p, rules in platforms_data.items()
        ]

        volume_weight = inp.length_cm * inp.width_cm * inp.height_cm / 6000
        return {
            "chargeable_weight_kg": round(max(inp.weight_kg, volume_weight), 3),
            "volume_weight_kg": round(volume_weight, 3),
            "fx_usd_cny": fx,
            "fx_source": fx_source,
            "platforms": [p.__dict__ for p in results],
        }

    def quick_check(self, cost_cny: float, weight_kg: float) -> dict[str, Any]:
        """快速检查：采购价 + 重量 → 返回直观的盈亏摘要。"""
        inp = EconomicsInput(cost_cny=cost_cny, weight_kg=weight_kg)
        result = asyncio.run(self.run(**inp.model_dump()))
        cheapest = min(result["platforms"], key=lambda p: p["break_even_price"])
        return {
            "cheapest_platform": cheapest["platform"],
            "cheapest_breakeven": cheapest["break_even_price"],
            "all_verdicts": {p["platform"]: p["verdict"] for p in result["platforms"]},
        }


__all__ = ["EconomicsSkill"]
