---
name: visual-agent
description: 视觉生成 Agent：根据商品理解结果 + 平台规则，生成符合平台规范的商品主图。触发词：生成主图、AI 出图、图片生成、视觉效果、商品图、主图。
version: 1.0.0
author: QianAn Team
tags: [visual, image-generation, e-commerce, compliance]
dependencies: [rules-engine, product-understanding]
---

# 视觉生成 Agent

## 职责

为每个平台生成符合规范的商品主图。优先使用"以图改图"（基于卖家上传的真实图片改写背景/构图），失败回退纯文生图。

## 生成策略

```
输入：Understanding + PlatformRules + [参考图]
  │
  ├─ ① accident 有图 → 以图改图（primary path）
  │     ├─ 组装以图改图 prompt（含参考图 + 平台规范）
  │     ├─ 调用百炼文生图 API（content=[{"text": ...}, {"image": ref_url}]）
  │     └─ 若失败 → 回退纯文生图
  │
  ├─ ② 无图 → 纯文生图（fallback path）
  │     ├─ 组装文生图 prompt（含商品名 + 卖点 + 平台规范）
  │     ├─ 调用百炼文生图 API
  │     └─ 生成失败 → 使用模板占位图
  │
  ├─ ③ 生成后验证（PIL 可选）
  │     ├─ 尺寸检查
  │     ├─ 白底检测
  │     └─ 不通过 → 最多重生成 2 次
  │
  └─ ④ 返回图片 URL 列表（写入 listing.images）
```

## 平台主图规范

| Platform | 尺寸 | 背景 | 商品占比 | 特殊要求 |
|----------|------|------|---------|---------|
| Amazon | 1000×1000 | 纯白 #FFF | ≥85% | 无文字/Logo/边框 |
| Shopee | 800×800 | 干净浅色 | ≥80% | 无水印/边框 |
| AliExpress | 800×800 | 白色 | ≥80% | 允许少量促销文字 |
| Lazada | 500×500 | 白色 | ≥75% | 无多余元素 |
| TikTok Shop | 1080×1080 | 品牌色/纯色 | ≥70% | 可带功能文字 |

## Prompt 工程

### 以图改图 Prompt

```
Reference image 1 (图1) is the real product photo. Keep the exact same product 
(shape, color, pattern, material, every detail) — do NOT redesign or reimagine it.
基于这张真实商品照生成电商主图：
商品：{product_name}
平台主图规范：{image_rules}
要求：保持商品本体与照片完全一致，仅按规范调整背景与构图；电商级布光，主体居中 
占画面 85% 以上，无水印、无边框、无文字，商业摄影质感。
```

### 纯文生图 Prompt

```
为电商主图生成一张高质量商品场景图：
商品：{product_name}
卖点：{selling_points}
平台主图规范：{image_rules}
要求：电商级构图，干净背景，主体居中占画面 85% 以上，无水印、无边框、无文字，
商业摄影质感。
```

## API 适配

百炼 Token Plan 网关文生图接口：
- 模型：`qwen-image-2.0` 或 `wan2.7-image`
- 接口：`/chat/completions`（注意：/images/generations 在该网关不可用）
- 以图改图参数：`content` 列表追加 `{"image": 参考图URL}`
- 图片返回位置：`response.choices[0].message.content[0]["image"]`

## 输出 Schema

```json
{
  "platform": "amazon",
  "images": [
    {
      "url": "https://dashscope-result-...",
      "width": 1000,
      "height": 1000,
      "generation_type": "img2img|text2img",
      "passed_checks": ["size", "white_bg"]
    }
  ],
  "primary_url": "https://...",
  "fallback_used": false,
  "retry_count": 0
}
```

## 降级方案

| 失败场景 | 降级策略 |
|---------|---------|
| 文生图 API 500/超时 | 回退 seller 原图 + 格式转换（切白底用 PIL） |
| 出图质量不达标（≥ 3 次） | 返回原图 + 标注 "AI 辅助 + 人工微调" |
| 无参考图且文生图失败 | 使用同品类模板占位图 |

## 诚实标签

如果使用了降级方案（非纯 AI 生成），在合规报告中诚实标注：
> "AI 辅助生成 + 人工微调" — 路演时说明这是 Demo 质量出图，真实环境会迭代提示词。

## 实现参考

核心逻辑与 `qianan/server/app/agents/visual.py` → `VisualAgent` class 保持 1:1 对应。
