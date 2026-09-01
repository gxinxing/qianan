---
name: copywriting
description: 文案生成 Agent：根据规则引擎输出的约束清单 + 商品理解结果，生成符合各平台规范的多语言 Listing 文案。触发词：生成文案、生成标题、翻译卖点、本地化文案、Amazon 标题、Shopee 文案。
version: 1.0.0
author: QianAn Team
tags: [copywriting, listing, localization, llm, self-healing]
dependencies: [rules-engine, product-understanding, compliance-check]
---

# 文案生成 Agent

## 职责

根据商品理解结果 + 平台规则约束 → 生成符合各平台规范的多语言 Listing 文案。每条文案生成后自动送 compliance-check 校验，发现 error 级问题自动自愈修订。

## 核心规则

1. **零违规词**：逐词检查 bannedWords 列表，一个都不能有
2. **字符不超限**：标题、描述严格控制在 maxLength 以内
3. **格式匹配**：Amazon 五点格式 × Shopee 富文本格式，各不相同
4. **非直译**：按目标市场购物习惯重新组织语言（如泰语用礼貌体、俄语用简洁陈述）
5. **A10 埋词**（Amazon）：标题自然融入高搜索量关键词，绝不堆砌

## 工作流程

```
输入：Understanding + Rules + Locales + Focus
  │
  ├─ 加载系统提示词（prompts/copywriting_system.md）
  ├─ 组装用户 prompt：商品理解 + 规则约束 + 输出格式要求 + 过往教训
  ├─ 调用 LLM（qwen3.7-max）生成文案
  ├─ 解析 JSON 输出 → PlatformListing
  ├─ 自动送 compliance-check 校验
  │    ├─ 通过 → 返回
  │    └─ 发现 error → 触发自愈修订循环
  │         ├─ 加载修订提示词（prompts/copywriting_revise_system.md）
  │         ├─ 调用 LLM 修订特定字段
  │         ├─ 复检合规
  │         └─ 最多修订 heal_budget 轮
  └─ 返回合规通过的 PlatformListing
```

## 多语言输出

每个 Listing 必须包含所有目标 locale 的本地化版本：

| Platform | Locales | 本地化优先级 |
|----------|---------|------------|
| Amazon | en-US, de-DE, ja-JP | 以英语为主，德/日语按需 |
| Shopee | th-TH, id-ID, vi-VN | 以站点语言为主 |
| AliExpress | en-US + 6 种语言 | 英语为主，辅以俄/西/法/葡/印尼/泰 |
| Lazada | en-US, th-TH, id-ID, vi-VN | 东南亚本地语言 |
| TikTok Shop | en-US | 以英语短视频风格为主 |

## 输出 Schema

```json
{
  "platform": "amazon",
  "locales": ["en-US"],
  "title": "Portable Blender Cup 380ml, USB-C Fast Charge...",
  "bullets": [
    "⚡ 10-Second Blending: High-speed motor...",
    "🧼 Easy to Clean: Detachable cup...",
    "🔋 USB-C Fast Charge: Full charge in 2 hours...",
    "🎒 Ultra Lightweight: Only 380g...",
    "🏆 Food-Grade Safe: BPA-free Tritan..."
  ],
  "description": "Full SEO-optimized product description...",
  "attributes": {
    "品牌": "示例品牌",
    "型号": "QB-380",
    "电压": "5V",
    "功率": "30W",
    "材质": "Tritan + Stainless Steel",
    "颜色": "White",
    "尺寸": "20x15x8cm",
    "重量": "380g",
    "产地": "CN",
    "认证": "FDA, BPA Free"
  },
  "aplus": [
    {
      "type": "headline",
      "title": "Your On-the-Go Nutrition Partner",
      "text": "Designed for busy lifestyles that refuse to compromise on health."
    },
    {
      "type": "grid",
      "title": "Why You'll Love It",
      "items": [
        {"title": "Instant Blending", "text": "10-second blend cycle for busy mornings"},
        {"title": "USB-C Charging", "text": "Compatible with any USB-C power source"},
        {"title": "Easy Cleanup", "text": "Detachable cup, dishwasher-safe parts"}
      ]
    },
    {
      "type": "compare",
      "title": "Specifications",
      "items": [
        {"label": "Capacity", "value": "380ml"},
        {"label": "Weight", "value": "380g"}
      ]
    },
    {
      "type": "story",
      "title": "Our Promise",
      "text": "We design practical products for modern life..."
    }
  ],
  "revised_count": 0,
  "compliance_passed": true
}
```

## 自愈联动

1. 生成完成后自动调用 compliance-check
2. 如果返回 error 级问题 → 进入自愈循环
3. 自愈策略：
   - 构造修订 prompt（含当前文案 + 问题清单 + 规则约束）
   - 调用 LLM 做定向修订（只修出问题的字段）
   - 修订后自动复检
   - 上限由 healer budget 控制（plan 阶段设定 0-3 轮）
   - 达到上限问题仍未清零 → 接受现状 + 记录

## 提示词模板

- 系统提示词：`prompts/copywriting_system.md`
- 修订提示词：`prompts/copywriting_revise_system.md`
- 动态注入： banned_words_block（规则中的禁用词组）+ focus（规划 Agent 的生成要点）+ past_lessons_block（记忆库召回）

## Mock 模式

无真实 LLM 时：
- 用英文 mock 数据生成合规文案
- 禁用词检查对 mock 禁用词表生效
- 自愈循环：本地剔除禁用词 + 截断超长字段
