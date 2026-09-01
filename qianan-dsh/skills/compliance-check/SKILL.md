---
name: compliance-check
description: 合规体检 Agent：对生成的 Listing 文案逐条校验各平台规则，输出 error/warn 级问题清单。触发词：合规检查、体检、预检、查禁用词、有没有问题、合规吗。
version: 1.0.0
author: QianAn Team
tags: [compliance, listing, validation, self-healing]
dependencies: [rules-engine]
---

# 合规体检 Agent

## 职责

对每个平台上架包执行**确定性合规校验**（38 项），产出结构化合规报告。这是千岸的核心护城河——合规通过代码校验实现，不依赖 LLM 判断，不产生幻觉。

## 工作原理

```
输入：PlatformListing（文案/属性/图片） + PlatformRules（平台规范）
  │
  ├─ ① 逐条遍历 complianceChecks[]（规则 JSON 中定义）
  │     ├─ length          → 字段长度 vs maxLength
  │     ├─ length_each     → 数组元素逐个检查
  │     ├─ count           → 数组元素数量 vs min/max
  │     ├─ banned_words    → 逐字段查禁用词库（正则边界匹配）
  │     ├─ required_attrs  → 类目必填属性完整性
  │     ├─ required_sections → 必备段落检测
  │     └─ image_spec      → PIL 实测（尺寸 + 四角白底检测）
  │
  └─ ② 聚合结果 → ComplianceIssue[] + compliance_passed 布尔
```

## 输入 Schema

```json
{
  "listing": {
    "platform": "amazon",
    "title": "Portable Blender Cup...",
    "bullets": ["bullet1", "bullet2", ...],
    "description": "Full description...",
    "attributes": {"品牌": "...", "型号": "..."},
    "images": ["https://...", "mock://image/..."],
    "locales": ["en-US"]
  },
  "rules": { /* 平台规则 JSON 完整内容（从 rules-engine skill 获取） */ },
  "category": "home_kitchen"
}
```

## 输出 Schema

```json
{
  "platform": "amazon",
  "passed": true,
  "issue_count": 0,
  "error_count": 0,
  "warn_count": 0,
  "issues": [
    {
      "check_id": "amz-title-001",
      "severity": "error",
      "field": "title",
      "message": "标题命中禁用词「guarantee」（claims 组）"
    }
  ]
}
```

## 38 项校验清单

### 标题校验（8 项）
| ID | 类型 | 字段 | 说明 |
|----|------|------|------|
| amz-title-001 | length | title | 长度 ≤ maxLength（200） |
| amz-title-002 | banned_words | title | 禁用词检测（claims/promotional/trademark） |
| amz-title-003 | length | title | 推荐长度范围建议（warn） |

### 描述校验（6 项）
| ID | 类型 | 字段 | 说明 |
|----|------|------|------|
| amz-desc-001 | length | description | 长度 ≤ maxLength（3000） |
| amz-desc-002 | banned_words | description | 全文禁用词扫描 |
| amz-desc-003 | required_sections | description | 必备段落检测 |

### 五点描述校验（5 项）
| ID | 类型 | 字段 | 说明 |
|----|------|------|------|
| amz-bullet-001 | count | bullets | 5 条数量检查 |
| amz-bullet-002 | length_each | bullets | 每条 ≤ 500 字符 |
| amz-bullet-003 | banned_words | bullets | 禁用词扫描 |

### 类目属性校验（6 项）
| ID | 类型 | 字段 | 说明 |
|----|------|------|------|
| amz-attr-001 | required_attrs | attributes | 必填字段完整 |
| amz-attr-002 | length | attributes | 属性值合理长度 |

### 主图规范校验（5 项）
| ID | 类型 | 字段 | 说明 |
|----|------|------|------|
| amz-img-001 | image_spec | mainImage | 尺寸 ≥ minSize（PIL 实测） |
| amz-img-002 | image_spec | mainImage | 四角白底检测 |
| amz-img-003 | image_spec | mainImage | 文字/边框/水印提示 |

### 禁用词大扫除（8 项）
按 bannedWords 分组逐字段扫描，支持：
- promotional：促销用语（sale, discount, coupon...）
- claims：绝对化用语（best, #1, guarantee...）
- restricted：受限词
- trademark：未授权品牌名
- locale-specific：各语言本地禁用词

## 自愈联动

- **error 级问题**（非主图）：自动触发 copywriting skill 的 revise 方法
- **warn 级问题**：报告但不阻断，可在 copywriting skill 中优化
- **主图规格问题**：无法通过文案解决，标记为需人工处理
- **修订后自动复检**：自愈完成 → 重新跑 compliance-check → 验证通过

## Mock 模式行为

无真实数据时进入 mock 模式：
- 返回确定性 mock issues 列表
- 图片检查跳过 PIL 实测，返回 "Mock 主图" 提示
- 禁用词检查使用硬编码的 demo 禁用词表

## 实现参考

核心逻辑与 `qianan/server/app/agents/compliance.py` → `ComplianceAgent` class 保持 1:1 对应。
