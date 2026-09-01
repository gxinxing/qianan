---
name: ideation
description: 选品灵感 Agent：根据目标市场和类目，结合趋势热词与竞品数据，生成 3 条具体、可落地、适合跨境上架的商品建议。触发词：选品、卖什么、推荐商品、有什么好卖的、选品建议。
version: 1.0.0
author: QianAn Team
tags: [ideation, product-research, trends, competitor-analysis]
dependencies: [rules-engine]
---

# 选品灵感 Agent

## 职责

解决卖家"不知道卖什么"的问题：根据目标市场和类目，结合实时趋势热词与竞品价格带数据，生成 3 条具体、差异化、可快速上架的商品建议。

## 工作流程

```
输入：market + category + [trends] + [competitor_band]
  │
  ├─ ① 检查可用数据源
  │     ├─ trends-hot skill → 实时搜索热词（已装才调用）
  │     └─ competitor-band skill → 类目价格带（已装才调用）
  │
  ├─ ② 组装 prompt：
  │     ├─ 系统提示词（prompts/ideation_system.md）
  │     ├─ 市场背景说明（MARKETS 映射）
  │     ├─ 类目方向说明（CATEGORIES 映射）
  │     └─ 可选：趋势热词注入 + 竞品价格带注入
  │
  ├─ ③ 调用 LLM 生成 3 条建议
  ├─ ④ 解析 JSON → 验证字段完整性
  └─ ⑤ 返回 suggestions[]（最多 3 条）
```

## 支持的市场与类目

### 市场

| Key | 描述 | 平台特征 |
|-----|------|---------|
| us | 美国市场 | Amazon 为主，客单价中高，重视合规与品牌感 |
| sea | 东南亚市场 | Shopee / Lazada / TikTok Shop，价格敏感、内容种草强 |
| global | 全球市场 | AliExpress，高性价比，多语言多地区 |

### 类目

| Key | 描述 |
|-----|------|
| electronics | 3C / 小家电（体积小、物流友好） |
| home_kitchen | 家居 / 厨房（高频消耗、复购率高） |
| apparel | 服饰 / 配饰（尺码压力小、退货率可控） |

## 输入 Schema

```json
{
  "market": "sea",
  "category": "electronics",
  "trends": ["wireless charger", "portable fan", "usb-c"],
  "competitor_band": {
    "price_min": 5.99,
    "price_max": 19.99,
    "currency": "USD",
    "samples": ["Mini Neck Fan 4000mAh", "Clip-on USB Light"]
  }
}
```

## 输出 Schema

```json
{
  "suggestions": [
    {
      "product_name": "MagSafe 磁吸车载手机支架 15W",
      "reason": "东南亚电动车市场爆发，车载配件需求年增 60%，现有竞品多为普通夹式",
      "selling_points": "磁吸即贴；15W 快充；360° 旋转；兼容 MagSafe 手机壳",
      "category": "electronics",
      "estimated_margin": 0.25
    },
    {
      "product_name": "可折叠硅胶沥水架 浴室置物架",
      "reason": "居家整理类搜索量稳定上升，马来/泰国站点同类竞品少",
      "selling_points": "免打孔；可折叠收纳；承重 5kg；食品级硅胶",
      "category": "home_kitchen",
      "estimated_margin": 0.35
    },
    {
      "product_name": "冰丝防晒面罩全脸遮阳护颈",
      "reason": "东南亚全年高温，UV 防护意识上升，客单价低决策快",
      "selling_points": "UPF50+；冰丝凉感；护颈一体；可水洗反复使用",
      "category": "apparel",
      "estimated_margin": 0.45
    }
  ],
  "trend_source": "live|mock",
  "competitor_band_source": "live|mock"
}
```

## 每条建议必须包含

- **product_name**: 具体商品名（含关键规格/参数）
- **reason**: 推荐理由（含趋势数据支撑 + 竞品差异化空间）
- **selling_points**: 3-5 条核心卖点（英文，可直接用于 copywriting skill 生成阶段）
- **category**: 推荐类目（从三个限定类目选一）
- **estimated_margin**: 预估毛利率（0-1），供 economics skill 参考

## 数据降级策略

| 连接器 | 未安装行为 | 影响 |
|--------|-----------|------|
| trends-hot | 跳过热词注入，基于模型通用知识推荐 | 建议质量略降，不影响流程 |
| competitor-band | 跳过价格带数据 | 建议照常生成，缺少价格差异化标注 |

降级通过**静默降级**实现——不报错、不中断、不影响主流程。

## Mock 模式

未安装 LLM / 真实 API 不可用时，返回每个类目 3 条预定义的高确定性 demo 建议。

## 实现参考

核心逻辑与 `qianan/server/app/agents/ideation.py` → `IdeationAgent` class 保持 1:1 对应。
