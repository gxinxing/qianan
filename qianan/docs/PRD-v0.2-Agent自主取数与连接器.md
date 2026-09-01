# PRD v0.2 · Agent 自主取数与连接器体系

日期：2026-09-01 ｜ 状态：已审计，进入实现

## Project DNA

千岸不是「多平台上架表单生成器」，而是**会自己去查数据、用数据做决策、把决策过程摊开给你看的跨境上新 Agent**。

AI 能力的三个可见性判据（评委任意其一感知不到，即为本 PRD 失败）：

1. **自主取数**：Agent 在规划阶段自行决定调用外部连接器（汇率/趋势/竞品/物流），不是人填表单喂数据。
2. **数据驱动产出**：文案关键词来自真实趋势词、利润判定用实时汇率、选品建议附搜索量依据。
3. **决策留痕**：trace 中出现连接器调用行（查了什么 → 查到什么 → 怎么用的），结果页可复核。

## First Action Path

用户一句话 → Agent 自主规划并调用连接器取数 → 生成合规上架包 → trace 展示「取数-决策-产出」链路。

## 铁腕审计记录

| 功能点                                              | 裁决       | 理由                                              |
| ------------------------------------------------ | -------- | ----------------------------------------------- |
| 连接器声明式 HTTP 机制（manifest `type:"http"`）           | ✅ 保留     | 自主取数的基础设施，无它一切免谈                                |
| 4 个数据源连接器（汇率/趋势/竞品/物流）                           | ✅ 保留     | 用户全选；3 个免 key 真实 API + 物流静态表演示「换 endpoint 即接货代」 |
| 连接器安装状态 = 能力点亮开关（economics/ideation 依赖安装态启用实时数据） | ✅ 保留     | 让「装/卸连接器」有真实产品语义，加号不再是摆设                        |
| plan 阶段工具注入 + trace 留痕                           | ✅ 保留     | 已有管线天然支持，增量极小                                   |
| 连接器「试运行」弹窗                                       | ❌ 驳回     | 调试工具，表单思维，稀释 AI 叙事；降级为安装时后端 ping 一次显示状态灯        |
| 连接器独立管理大 UI（弹窗/多步向导）                             | ❌ 驳回     | 复用 Agent 中心现有技能区，一行卡片 + 安装/卸载                   |
| 竞品价格自动填入 economics market\_price                 | ❌ 驳回（本轮） | 抓取噪声大、字段映射复杂；竞品连接器仅由 Agent 按需调用，不进表单            |
| economics 页报价对比大改                                | ❌ 驳回     | 只加数据来源徽标，一行字                                    |

## Technical Constraints

**Data Model（新增/变更）**

* `SkillManifest.tools[].type`：`"prompt" | "http" | "static"`（默认 prompt）

* http 工具字段：`url`（支持 `{param}` 占位）、`method`、`params`、`headers`、`extract`（点路径取值映射，可选）、`timeout_s`

* static 工具字段：`data`（任意 JSON，原样返回）、`note`

* `EconomicsResult.fx_source`：`"live" | "builtin"`

* `IdeationResult.trend_source`：`"google_trends" | "model_prior"`；`trends[]`：`{keyword, traffic}`

**State Machine**

* 连接器生命周期：`registry（可安装）→ installed（已装，工具注册，能力点亮）→ uninstalled（回滚，工具注销，能力熄灭）`

* 外部调用失败：`live → fallback（静默回退：汇率回 7.2、趋势回模型先验）+ trace 标记`

**接口约定**

* 实时汇率：`open.er-api.com/v6/latest/{base}`（免 key，TTL 缓存 6h）

* 趋势热词：`trends.google.com/trending/rss?geo={geo}`（免 key，RSS，正则解析 title + approx\_traffic，TTL 1h）

* 竞品参考价：`fakestoreapi.com/products`（免 key）

* 物流报价：static 表演数据，manifest 标注「演示数据」

## Feature Spec

1. **HTTP 型连接器引擎**（`skill_store.py`）：manifest 校验扩展 + `_make_http_tool()` 真实 handler（requests + 模板插值 + 8s 超时 + 结构化错误文本）+ `_make_static_tool()`。
2. **内置 4 连接器清单**（`data/skills/registry/`）：`fx-rates`、`market-trends`、`competitor-price`、`logistics-quote`，manifest 含 `kind:"connector"`。
3. **业务点亮逻辑**（`extdata.py` 新增）：`live_fx()`（TTL+回退）、`hot_keywords(geo)`（RSS 解析+回退）；仅在对应连接器已安装时启用，`economics` 返回 `fx_source`，`ideation` 返回 `trend_source + trends`。
4. **Agent 自主调用**：plan 阶段已有 `skill_tools()` 注入，连接器安装即自动进入规划器工具箱；trace 自动留痕工具调用行。
5. **前端可见性**：

   * Agent 中心技能区改「技能与连接器」，卡片带 `HTTP API / PROMPT / STATIC` 类型徽标 + 状态灯；

   * 选品卡片显示趋势词依据（或「模型先验」标注）；

   * 测算结果显示汇率来源徽标（「实时 · exchangerate-api」/「内置基准」）。
6. **演示剧本资产**：出厂预装 3 个连接器，`logistics-quote` 留作现场「加号安装 → Agent 立刻会查运费」演示。

## Not-To-Do List

* ❌ 严禁做连接器试运行表单/弹窗

* ❌ 严禁做连接器多步配置向导、独立管理页

* ❌ 严禁把竞品抓取接进 economics 表单自动填充

* ❌ 严禁引入需 API key 的数据源（本轮全部免 key 或 static）

* ❌ 严禁为接 API 重构现有技能/规则管线（只做增量扩展）

