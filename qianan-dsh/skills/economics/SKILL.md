---
name: economics
description: 单位经济测算 Agent：根据商品参数（成本、重量、尺寸）+ 目标平台费率，计算各平台的保本价、建议售价、净利和盈亏判断。触发词：算利润、单位经济、定价、盈亏、赚不赚钱、保本价、建议价。
version: 1.0.0
author: QianAn Team
tags: [economics, pricing, unit-economics, cross-border]
dependencies: [rules-engine]
---

# 单位经济测算 Agent

## 职责

帮卖家判断一个商品在目标平台"能不能赚钱"。输入卖家侧事实（成本/重量/包装），输出每平台的保本价、建议售价、单件净利、盈亏平衡与判定。

**此 skill 不调用任何 LLM——纯确定性数学引擎。**

## 输入 Schema

```json
{
  "cost_cny": 12.0,
  "weight_kg": 0.3,
  "length_cm": 20,
  "width_cm": 15,
  "height_cm": 8,
  "target_margin": 0.15,
  "first_mile": "sea",
  "market_price_min": 12,
  "market_price_max": 25,
  "fixed_cost_cny": 3000
}
```

| 字段 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| cost_cny | float | — | 采购单价（CNY） |
| weight_kg | float | — | 商品实重（kg） |
| length_cm | float | — | 包装长度 |
| width_cm | float | — | 包装宽度 |
| height_cm | float | — | 包装高度 |
| target_margin | float | 0.15 | 目标净利率（对净收入） |
| first_mile | string | "sea" | 头程：sea 海运 ¥8/kg / air 空运 ¥28/kg |
| turnover_months | float | 2.0 | 海外仓资金周转月数 |
| fixed_cost_cny | float | 0 | 认证/打样/拍摄一次性投入 |
| market_price_min | float? | null | 市场带最低价（USD） |
| market_price_max | float? | null | 市场带最高价（USD） |

## 计算链路

```
输入参数
  │
  ├─ 计费重 = max(实重 kg, 体积重 kg = L×W×H/6000)
  ├─ 汇率 = 实时（fx-live skill） 或 内置 7.2 兜底
  ├─ 逐平台计算：
  │     ├─ 采购 = cost_cny / 汇率
  │     ├─ 头程 = 计费重 × 头程单价 / 汇率
  │     ├─ 尾程 = rules.economics.fulfillment.fee（FBA 阶梯/标准）
  │     ├─ 仓储 = 体积(m³) × 月租单价 × 周转月数
  │     ├─ 退货损失 = 退货率 × (退货手续费 + 50% 可回收残值)
  │     ├─ 佣金 = 净收入 × 佣金率
  │     ├─ 广告 = 净收入 × 广告费率
  │     ├─ VAT = 售价 - 净收入
  │     └─ 保本价 = 现金成本 / (1 - 佣金率 - 广告率) × (1 + VAT率)
  │
  └─ 建议价 = 现金成本 / (1 - 佣金率 - 广告率 - 目标净利率) × (1 + VAT率)
```

## 输出 Schema

```json
{
  "chargeable_weight_kg": 0.500,
  "volume_weight_kg": 0.240,
  "fx_usd_cny": 7.2,
  "fx_source": "live|builtin",
  "platforms": [
    {
      "platform": "amazon",
      "display_name": "Amazon US",
      "purchase": 1.67,
      "first_mile": 4.44,
      "last_mile": 3.88,
      "storage": 0.82,
      "return_loss": 0.38,
      "commission": 3.74,
      "ad": 3.74,
      "vat": 0.00,
      "profit": -2.67,
      "margin": -0.07,
      "break_even_price": 18.50,
      "suggested_price": 24.90,
      "bep_units": 120,
      "verdict": "yellow",
      "verdict_reason": "建议价高于市场带上限，需品牌溢价或降低成本"
    }
  ]
}
```

## 判定标准

| Verdict | 条件 |
|---------|------|
| green **可上** | 建议价 ≤ 市场带上限 且 净利率 ≥ 目标 |
| yellow **需溢价** | 建议价 > 市场带上限 或 净利率略低于目标 |
| red **放弃** | 保本价 > 市场带上限（成本倒挂） |

## 费用因子

| 费用项 | Amazon | Shopee | AliExpress | Lazada | TikTok Shop |
|--------|--------|--------|-----------|--------|------------|
| 佣金率 | 15% | 4% | 5% | 4% | 5% |
| 广告费率 | 10% | 10% | 10% | 10% | 15% |
| 退货率 | 8% | 5% | 7% | 6% | 10% |
| 尾程 | FBA 阶梯 | 平台 $2.5 | LS 标准 $3.5 | LMS $2.8 | 平台 $3.2 |
| 仓储 | $27/m³/月 | — | — | — | — |

费率来源：`data/rules/{platform}.json` → economics 块（Demo 估算值，公开文档整理）。

## 依赖

- **rules-engine skill**：加载各平台的 economics 块（佣金率/费率/退货率）
- **fx-live skill**（可选）：获取实时 USD/CNY 汇率；未安装则回退内置 7.2

## Mock 模式

使用内置费率表计算，无需外部依赖。输出与真实模式相同结构的 PlatformEconomics 数组。

## 实现参考

核心逻辑与 `qianan/server/app/economics.py` → `evaluate()` / `evaluate_platform()` 保持 1:1 对应。
