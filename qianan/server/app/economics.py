"""单位经济引擎：确定性数学，费率来自 rules/*.json 的 economics 块（demo 估算值）。

不做任何 LLM 调用——延续"规则库是唯一事实源"的原则。
输入卖家侧事实（采购价/重量/包装/目标净利率/市场带），输出每平台
保本价、建议价、单件净利、盈亏平衡销量与盈亏判定（红牌=成本倒挂，建议放弃）。

汇率由调用方注入（extdata.live_fx）：装了汇率连接器 = 实时汇率，
否则回退内置 7.2——测算引擎本身保持纯粹，不关心数据从哪来。
"""
from __future__ import annotations

from typing import Optional

from pydantic import BaseModel, Field

from .rules_store import all_platforms

USD_CNY = 7.2  # 内置兜底汇率（实时汇率连接器未安装/失败时使用）
FIRST_MILE_CNY_PER_KG = {"sea": 8.0, "air": 28.0}  # 头程海运/空运单价区间（demo）
SALVAGE_RATIO = 0.5  # 退货件残值假设：一半的采购+头程成本不可回收
MIN_DENOM = 0.05  # 分母保护：佣金+广告(+目标净利)吃掉 95% 以上售价时判定结构性亏损


class EconomicsInput(BaseModel):
    cost_cny: float = Field(gt=0, description="采购单价（CNY）")
    weight_kg: float = Field(gt=0, description="实重（kg）")
    length_cm: float = Field(gt=0)
    width_cm: float = Field(gt=0)
    height_cm: float = Field(gt=0)
    target_margin: float = Field(default=0.15, ge=0, le=0.5, description="目标净利率（对净收入）")
    first_mile: str = Field(default="sea", pattern="^(sea|air)$")
    turnover_months: float = Field(default=2.0, gt=0, description="海外仓资金周转月数")
    fixed_cost_cny: float = Field(default=0.0, ge=0, description="一次性投入：认证/打样/拍摄（CNY）")
    market_price_min: Optional[float] = Field(default=None, ge=0, description="市场带最低价（USD，人工比价输入）")
    market_price_max: Optional[float] = Field(default=None, ge=0, description="市场带最高价（USD）")


class PlatformEconomics(BaseModel):
    platform: str
    display_name: str
    currency: str = "USD"
    purchase: float
    first_mile: float
    last_mile: float
    storage: float
    return_loss: float
    commission: float
    ad: float
    vat: float
    profit: float
    margin: float
    break_even_price: float
    suggested_price: float
    bep_units: Optional[int] = None
    verdict: str  # green | yellow | red
    verdict_reason: str


class EconomicsResult(BaseModel):
    chargeable_weight_kg: float
    volume_weight_kg: float
    fx_usd_cny: float
    fx_source: str = "builtin"  # live=实时汇率连接器 | builtin=内置兜底
    platforms: list[PlatformEconomics]


def _last_mile(rules: dict, chargeable_kg: float) -> float:
    ful = rules.get("economics", {}).get("fulfillment", {})
    if ful.get("type") == "fba_tiers":
        tiers = ful.get("tiers", [])
        for tier in tiers:
            if chargeable_kg <= float(tier["maxKg"]):
                return float(tier["fee"])
        top = tiers[-1]
        return float(top["fee"]) + (chargeable_kg - float(top["maxKg"])) * 1.2
    return float(ful.get("fee", 1.2))


def _verdict(
    item: PlatformEconomics,
    inp: EconomicsInput,
    commission_rate: float,
    ad_rate: float,
    cash_cost: float,
) -> tuple[str, str]:
    if inp.market_price_min is not None and inp.market_price_max is not None:
        lo, hi = inp.market_price_min, inp.market_price_max
        if item.break_even_price > hi:
            return (
                "red",
                f"保本价 ${item.break_even_price:.2f} 高于市场带最高 ${hi:.2f}——成本倒挂，"
                "建议放弃或换供应链/降包装档位",
            )
        mid = (lo + hi) / 2
        net_mid = mid / (1 + item.vat) * (1 - commission_rate - ad_rate)
        profit_mid = net_mid - cash_cost
        if profit_mid <= 0:
            return "red", f"按市场带中位价 ${mid:.2f} 销售仍亏损，该市场无利可图"
        if item.suggested_price > hi:
            return (
                "yellow",
                f"建议价 ${item.suggested_price:.2f} 高于市场带，需卖点差异化或品牌溢价支撑",
            )
        return "green", f"建议价落在市场带内，净利率 {item.margin * 100:.1f}%"
    return (
        "green",
        f"保本价 ${item.break_even_price:.2f}，建议价按目标净利率 {inp.target_margin * 100:.0f}% 反推"
        + (f"，盈亏平衡销量 {item.bep_units} 件" if item.bep_units else ""),
    )


def evaluate_platform(
    platform: str, rules: dict, inp: EconomicsInput, fx: float = USD_CNY
) -> PlatformEconomics:
    eco = rules.get("economics", {})
    volume_weight = inp.length_cm * inp.width_cm * inp.height_cm / 6000
    chargeable = max(inp.weight_kg, volume_weight)

    purchase = inp.cost_cny / fx
    first_mile = chargeable * FIRST_MILE_CNY_PER_KG[inp.first_mile] / fx
    last_mile = _last_mile(rules, chargeable)
    volume_m3 = inp.length_cm * inp.width_cm * inp.height_cm / 1_000_000
    storage = (
        volume_m3
        * float(eco.get("fulfillment", {}).get("monthlyStoragePerCubicMeter", 15.0))
        * inp.turnover_months
    )
    commission_rate = float(eco.get("commissionRate", 0.15))
    ad_rate = float(eco.get("adTacosDefault", 0.15))
    return_rate = float(eco.get("returnRateDefault", 0.05))
    handling = float(eco.get("returnHandlingFee", 1.0))
    vat = float(eco.get("vatRate", 0.0))

    return_loss = return_rate * (
        handling + SALVAGE_RATIO * (purchase + first_mile)
    )
    cash_cost = purchase + first_mile + last_mile + storage + return_loss

    break_even = cash_cost / (1 - commission_rate - ad_rate) * (1 + vat)
    margin_denom = 1 - commission_rate - ad_rate - inp.target_margin
    if margin_denom <= MIN_DENOM:
        suggested = break_even * 1.5
    else:
        suggested = cash_cost / margin_denom * (1 + vat)

    net_revenue = suggested / (1 + vat)
    commission_amt = net_revenue * commission_rate
    ad_amt = net_revenue * ad_rate
    vat_amt = suggested - net_revenue
    profit = net_revenue * (1 - commission_rate - ad_rate) - cash_cost
    margin = profit / net_revenue if net_revenue > 0 else 0.0

    fixed_usd = inp.fixed_cost_cny / fx
    bep_units = int(fixed_usd / profit) if profit > 0 and fixed_usd > 0 else None

    item = PlatformEconomics(
        platform=platform,
        display_name=rules.get("displayName", platform),
        purchase=round(purchase, 2),
        first_mile=round(first_mile, 2),
        last_mile=round(last_mile, 2),
        storage=round(storage, 2),
        return_loss=round(return_loss, 2),
        commission=round(commission_amt, 2),
        ad=round(ad_amt, 2),
        vat=round(vat_amt, 2),
        profit=round(profit, 2),
        margin=round(margin, 4),
        break_even_price=round(break_even, 2),
        suggested_price=round(suggested, 2),
        bep_units=bep_units,
        verdict="green",
        verdict_reason="",
    )
    item.verdict, item.verdict_reason = _verdict(
        item, inp, commission_rate, ad_rate, cash_cost
    )
    return item


def evaluate(
    inp: EconomicsInput, fx: float = USD_CNY, fx_source: str = "builtin"
) -> EconomicsResult:
    volume_weight = inp.length_cm * inp.width_cm * inp.height_cm / 6000
    platforms = [
        evaluate_platform(platform, rules, inp, fx)
        for platform, rules in all_platforms().items()
    ]
    return EconomicsResult(
        chargeable_weight_kg=round(max(inp.weight_kg, volume_weight), 3),
        volume_weight_kg=round(volume_weight, 3),
        fx_usd_cny=fx,
        fx_source=fx_source,
        platforms=platforms,
    )
