---
name: product-understanding
description: 商品理解 Agent：分析卖家上传的商品图和/或卖点文本，提取品类、材质、核心卖点、目标受众、关键词等结构化信息。触发词：分析商品、理解商品、提取卖点、这是什么产品、商品分类。
version: 1.0.0
author: QianAn Team
tags: [product-understanding, vision, nlp, classification]
dependencies: [rules-engine]
---

# 商品理解 Agent

## 职责

将卖家的原始输入（商品图 + 中文卖点描述）转化为**结构化的商品档案**，供下游各 skill（copywriting / visual-agent / economics）统一消费。

## 工作流程

```
输入：GenerateRequest（商品名 + 卖点 + 图 + 类目）
  │
  ├─ ① 优先路径：视觉理解（若配置了 VL 模型且有图）
  │     ├─ 调用 Qwen-VL 视觉理解 API
  │     ├─ 传入商品图 + 卖点文本
  │     └─ 解析模型返回的 JSON → Understanding
  │
  ├─ ② 回退路径：纯文本分析
  │     ├─ 加载系统提示词（prompts/understanding_system.md）
  │     ├─ 调用 LLM（qwen3.7-max）
  │     └─ 解析 JSON 输出 → Understanding
  │
  └─ ③ Mock 模式：基于输入文本做确定性解析
        ├─ 类目：使用用户提供的 category
        ├─ 卖点：按分隔符切分输入文本
        ├─ 关键词：从商品名分词
        └─ 材质/品牌：设为默认值
```

## 输入 Schema

```json
{
  "product_name": "便携榨汁杯 380ml",
  "selling_points": "USB-C 快充，10 秒出汁，杯身可拆洗，仅 380g",
  "category": "home_kitchen",
  "image_url": "https://... (可选)",
  "image_base64": "data:image/... (可选)"
}
```

## 输出 Schema

```json
{
  "category": "home_kitchen",
  "product_type": "portable blender",
  "material": "Tritan + stainless steel blade",
  "attributes": {
    "品牌": "",
    "颜色": "white",
    "容量": "380ml"
  },
  "selling_points": [
    "USB-C fast charge",
    "10-second blending",
    "detachable for easy clean",
    "ultra lightweight 380g"
  ],
  "target_audience": "office workers, fitness enthusiasts, college students",
  "keywords": ["portable", "blender", "USB-C", "personal", "smoothie", "380ml"]
}
```

## 字段详细说明

| 字段 | 类型 | 约束 | 说明 |
|------|------|------|------|
| category | string | 三选一 | electronics / home_kitchen / apparel |
| product_type | string | 英文短语 | 产品类型（如 portable blender） |
| material | string | 英文 | 主要材质 |
| attributes | dict | 自由 | 关键属性卡片 |
| selling_points | list[str] | 3-5 条 | 核心卖点（从用户描述提取） |
| target_audience | string | 英文 | 目标受众描述 |
| keywords | list[str] | 5-8 个 | 搜索关键词（每词 2-6 字） |

## 类目限定

仅限三个场景一核心类目（与大赛聚焦一致）：
- `electronics`：3C / 小家电
- `home_kitchen`：家居 / 厨房用品
- `apparel`：服饰 / 配饰

## 分析规则

1. **卖点优先**：用户描述的优先级 > 视觉观察
2. **不美化**：selling_points 从用户原话提取，不做营销化润色
3. **材质可推断**：未明确说明时根据产品类型推断常见材质
4. **关键词覆盖**：覆盖品牌/功能/场景/属性/规格维度

## Mock 模式

无 LLM/模型时：
- 类目：使用用户传入 category
- product_type：商品名小写
- material："ABS + stainless steel"
- selling_points：按中英文分号切分，最多 5 条
- keywords：商品名分词，最多 6 个

## 实现参考

核心逻辑与 `qianan/server/app/agents/understanding.py` → `ProductUnderstandingAgent` class 保持 1:1 对应。
