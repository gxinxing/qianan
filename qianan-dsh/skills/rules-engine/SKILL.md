---
name: rules-engine
description: 规则引擎 Agent：读取平台规则库 JSON，返回该平台的完整约束清单。这是千岸的核心护城河——结构化规则 + 确定性逻辑，不使用 LLM。触发词：查规则、合规要求、平台规范、Amazon 规则、Shopee 规则、速卖通规则。
version: 1.0.0
author: QianAn Team
tags: [rules-engine, compliance, platform-rules, structured]
dependencies: []
---

# 规则引擎 Agent

## 职责

为选中的每个平台加载对应的**结构化规则 JSON**，输出约束清单供文案 Agent 和经济测算 Agent 使用。

**此 skill 不使用 LLM——纯确定性 JSON 规则库 + 逻辑代码。这是千岸的护城河。**

## 文件结构

```
data/rules/
  amazon.json      ← 平台规则（唯一事实源）
  shopee.json
  aliexpress.json
  lazada.json
  tiktokshop.json

data/skills/
  installed/       ← 已安装技能的规则补丁（overlay 形式）
    fx-live.json
    trends-hot.json
    competitor-band.json
    eu-gpsr.json
```

规则加载流程：
1. 读取 `data/rules/{platform}.json`
2. 检查 `data/skills/installed/` 中是否有该平台的规则补丁
3. 若有 → 以 overlay 形式合并（只追加禁词组/检查项，不改源文件）
4. 缓存结果（lru_cache），安装/卸载技能后调 `cache_clear()`

## 输入 Schema

```json
{
  "platforms": ["amazon", "shopee", "aliexpress", "lazada", "tiktokshop"],
  "category": "home_kitchen"
}
```

## 输出 Schema

```json
{
  "amazon": {
    "platform": "amazon",
    "displayName": "Amazon US (Deep Dive)",
    "locales": ["en-US"],
    "constraints": {
      "title": {
        "maxLength": 200,
        "recommendedLength": [150, 180],
        "formula": "Brand + Core Keyword + Differentiator + Material/Feature + Use Case",
        "mustIncludeKeywords": true
      },
      "bullets": {
        "count": 5,
        "maxLengthPer": 500,
        "style": "symbol_started"
      },
      "description": {
        "maxLength": 3000,
        "type": "html_enhanced"
      },
      "mainImage": {
        "background": "white",
        "minWidth": 1000,
        "minHeight": 1000,
        "noText": true,
        "noWatermark": true,
        "noBorder": true,
        "productFillRatio": 0.85
      }
    },
    "bannedWords": {
      "promotional": ["sale", "free shipping", "discount", ...],
      "claims": ["best", "#1", "top", "guarantee", ...],
      "restricted": ["diet pill", "weight loss", ...]
    },
    "requiredAttributes": {
      "electronics": ["品牌", "型号", "电压", "功率", "材质", "颜色", "尺寸", "重量", "产地", "认证"]
    },
    "locales": ["en-US"],
    "complianceChecks": [...],
    "economics": {
      "commissionRate": 0.15,
      "adTacosDefault": 0.10,
      "returnRateDefault": 0.08,
      ...
    }
  }
}
```

## 支持的 5 个平台

| Platform Key | Display Name | Demo 深度 | 差异化点 |
|-------------|-------------|---------|---------|
| amazon | Amazon US | Deep | 标题≤200 字符、A10 埋词、五点、A+ 内容、FBA 阶梯尾程 |
| shopee | Shopee TH/ID | Deep | 主图禁水印/边框、泰语印尼语本地化、本地禁用词 |
| aliexpress | AliExpress Global | Reuse | 多语标题 + 类目属性、目的地关税 |
| lazada | Lazada SEA | Reuse | 东南亚多语适配、SST/GST |
| tiktokshop | TikTok Shop US | Simple | 商品卡文案 + 短视频脚本模板、1080x1080 |

## 约束提取方法：constraint_brief()

供 copywriting skill 调用，将完整规则压缩为给 LLM 的自然语言约束：

```
标题 ≤200 字符，公式：Brand + Core Keyword + Differentiator + Material/Feature + Use Case；
五点描述 5 条，每条 ≤500 字符；
描述 ≤3000 字符；
禁止使用以下词语：sale, free shipping, discount, best, #1, guarantee...
```

## 平台规则 JSON Schema

```json
{
  "version": "v1",
  "platform": "amazon",
  "displayName": "Amazon US",
  "updated": "2025-09",
  "demoDepth": "deep|reuse|simple",
  "locales": ["en-US"],
  "marketplaces": ["amazon.com"],
  "title": { "maxLength": number, "formula": string, ... },
  "bullets": { "count": number, "maxLengthPer": number, ... },
  "description": { "maxLength": number, ... },
  "mainImage": { "background": string, "minWidth": number, ... },
  "categoryAttributes": { "electronics": [string], ... },
  "bannedWords": { "group_name": [string], ... },
  "complianceChecks": [ { "id": string, "type": string, ... } ],
  "economics": { "commissionRate": number, ... }
}
```

## 实现参考

核心逻辑与 `qianan/server/app/agents/rules_engine.py` → `RulesEngineAgent` class + `qianan/server/app/rules_store.py` → `load_rules()` 保持 1:1 对应。
