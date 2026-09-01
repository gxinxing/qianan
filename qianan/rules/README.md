# 规则库（千岸核心资产）

每个平台一个 JSON 文件，统一遵循 `rules.v1` schema。规则引擎（非 LLM）读取本目录，
为文案 / 视觉 / 合规三个 Agent 提供结构化约束。

## 设计原则

1. **规则引擎不是 LLM**：本目录是结构化事实，代码直接消费，杜绝幻觉。
2. **合规检查可执行**：`complianceChecks` 里每一条都对应合规体检 Agent 的一个真实校验函数
   （长度、数量、禁词、图片规范、必填属性），不是摆设。
3. **只收录公开规范**：来源为各平台卖家中心公开文档，人工整理 + LLM 辅助提取，不爬平台数据。
4. **持续校对**：`updated` 字段记录最近核对日期；上架前应以目标站点最新官方文档复核。

## Schema（rules.v1）

| 字段 | 说明 |
|---|---|
| `platform` / `displayName` | 平台标识与展示名 |
| `demoDepth` | `deep` 做深 / `reuse` 机制复用 / `simple` 简化（对应复赛策略） |
| `locales` | 输出语言列表，文案 Agent 按此本地化 |
| `title` | 标题约束：长度、公式、禁忌 |
| `bullets` / `description` | 五点 / 描述约束（无此形态的平台可省略） |
| `mainImage` / `gallery` | 主图与图片组规范 |
| `aPlus` / `videoScript` | 平台特有产出物（A+ 模块 / 短视频脚本） |
| `categoryAttributes` | 类目 → 必填属性映射（Demo 覆盖 3C / 家居 / 服饰） |
| `bannedWords` | 禁用词表（可分组，见下） |
| `complianceChecks` | 合规体检项，驱动合规体检 Agent |

### bannedWords 分组

```json
"bannedWords": {
  "promotional": ["free shipping", "..."],
  "claims": ["guarantee", "..."],
  "restricted": ["antibacterial", "..."]
}
```

`restricted` 组用于"看似普通但会触发平台审查"的词（如 Amazon 把抗菌类宣称按农药类目审查），
是 Demo 里最能体现合规价值的彩蛋。

### complianceChecks 类型

| type | 参数 | 执行方式 |
|---|---|---|
| `length` | field, max, min? | 字符数校验 |
| `length_each` | field, max | 数组元素逐条校验 |
| `count` | field, min, max | 数组数量校验 |
| `banned_words` | fields, dict(组名), locale? | 词表匹配（不区分大小写，词边界） |
| `image_spec` | minWidth, minHeight, background, noText, noWatermark, noBorder | 尺寸走代码；背景/水印等由 Qwen-VL 判图 |
| `required_attrs` | — | 按类目核对必填属性是否齐全 |
| `locale_coverage` | locales | 每个目标语言都要有产出 |

`severity`: `error`（会被平台拒收/下架风险）/ `warn`（影响转化或被限流）。
