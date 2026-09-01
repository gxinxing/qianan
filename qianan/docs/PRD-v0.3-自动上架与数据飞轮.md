# PRD v0.3 · 自动上架与数据飞轮

日期：2026-09-01 ｜ 状态：已审计，待确认后进入实现

## Project DNA

千岸的闭环缺最后一公里：目前系统止于「下载 CSV」，上架动作仍发生在系统之外。本 PRD 把链路补成 **生成 → 人审 → Agent 执行上架 → 表现数据回流 → 数据驱动进化** 的完整飞轮。

三个可见性判据（评委任意其一感知不到，即为本 PRD 失败）：

1. **上架动作可见**：浏览器被 Agent 驱动，完成填表、传图、提交，返回 live URL，全程步骤级 trace 留痕。
2. **数据回流可见**：live 商品持续产生曝光/点击/转化，被 collector 拉回系统，看板可查。
3. **飞轮可见**：指标异常触发进化提案，提案 evidence 直接引用指标数据；人审批准后提示词/规则产生新版本，下一轮生成行为改变。

## First Action Path

结果页点「确认上架」→ Agent 驱动浏览器完成上架并回传 live URL → mock 后台指标模拟器开始产数 → collector 回流 → 异常触发进化提案 → 人审生效。

## 铁腕审计记录

| 功能点                                | 裁决    | 理由                                                                                                                                                                  |
| ---------------------------------- | ----- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| 用户确认闸口（approved 才允许建上架任务）          | ✅ 保留  | 人机协同的诚实边界，也是演示叙事的关键节点                                                                                                                                               |
| 上架执行器层（Publisher 抽象 + 状态机）         | ✅ 保留  | 闭环核心缺口，无此一切免谈                                                                                                                                                       |
| Playwright 驱动 mock 卖家后台（演示路径）      | ✅ 保留  | 自洽、可重复、零外网依赖；「看得见的自动上架」                                                                                                                                             |
| Chrome 扩展半自动回填（真实域名路径）             | ✅ 保留  | 复用现有 `QA_FILL` 协议，真实 Amazon 后台只回填不提交                                                                                                                                |
| 后台指标回流 + 异常检测                      | ✅ 保留  | 飞轮的数据入口                                                                                                                                                             |
| metrics 作为进化 Agent 第三证据源           | ✅ 保留  | 复用 evolution.py 提案机制，增量极小                                                                                                                                           |
| Computer Use 全自动控制真实电脑             | ⚠️ 裁剪 | 用户诉求的 DNA 是「执行可见、错误可回溯」，该性质由有头浏览器 + steps\[] + 截图序列确定性交付；Computer Use 的真正价值在于无 API/无协议平台的通用通道，但真实平台有 2FA/验证码/反爬、现场翻车概率高——保留 `ComputerUsePublisher` 接口占位 + flag 默认关闭 |
| 真实平台写 API（SP-API / Shopee OpenAPI） | ❌ 驳回  | 开发者资质审核以周计，黑客松周期内不可达；接口契约预留，实现留 Roadmap                                                                                                                             |
| 真正的强化学习（RLHF / 策略网络训练）             | ❌ 驳回  | 无训练基础设施且 demo 不可展示；以「提案机制 + 提示词/规则版本化 + 人审回滚」落地策略迭代——工程上等价于可审计的 RL，且每步留痕                                                                                            |
| 无人值守自动上架、自动改写                      | ❌ 驳回  | 上架与进化均保留人工闸口，系统不做无人决策                                                                                                                                               |

## Technical Constraints

**Data Model（新增）**

* `PublishJob`：`{ job_id, task_id, platform, executor, status, attempts, last_error, live_url, published_at, steps[] }`

  * `executor`：`"mock_browser" | "extension_assist" | "computer_use"`

  * `steps[]`：`{ ts, action, detail, screenshot? }`（打开页面/填字段/传图/提交/live 确认）

* `MetricsRecord`：`{ job_id, sku, platform, ts, impressions, clicks, conversions }`；`ctr` 为派生字段不落盘

* 复用不变：`Feedback`、`Proposal`（仅 evidence 来源扩展）

**State Machine**

* PublishJob：`queued → running → live | failed`；`failed → running`（retry ≤ 2，指数退避）

* 飞轮：`metrics_ingested → anomaly_detected → proposal_pending → applied | rejected`；applied 后可 rolled\_back（已有能力）

**可观测性约束（源于用户核心诉求：拒绝黑盒，错误可回溯）**

* 三条上架通道对比：平台写 API 能力最强但纯黑盒（已驳回）；Computer Use 通用性最强，但可见性停留在「人盯屏幕」，回溯靠录像而非结构化日志；Playwright 有头 + 协议驱动同时满足可见（屏幕实时）与可回溯（结构化 `steps[]` + 截图序列）——故为演示主路径。

* 任何 executor 的每次动作必须写 `steps[]` 并截图；演示一律有头模式；严禁静默执行路径。

**异常基线（V0.3 硬编码，不进配置系统）**

* `ctr < 0.02` 且 `impressions ≥ 200` → anomaly：`low_ctr`

* `conversions = 0` 且 `clicks ≥ 50` → anomaly：`zero_conversion`

## Feature Spec

1. **上架执行器层** **`server/app/publisher/`**

   * `BasePublisher.publish(listing, artifacts) -> PublishResult` 统一接口。

   * `MockBrowserPublisher`：Playwright 驱动 `mock-seller-central.html`，按 `data-sc-field` 协议填表、上传主图、点击提交；逐步写 `steps[]` 并截图；演示用有头模式，CI 用无头。

   * `ExtensionAssistPublisher`：向扩展发 `QA_FILL`，真实域名半自动回填；提交键永远属于人。

   * `ComputerUsePublisher`：接口占位，feature flag 默认关；仅声明与 Anthropic Computer Use 的适配点。
2. **mock 卖家后台增强**

   * 提交后生成 live listing 页（分配 `listing_id`，展示标题/五点/主图）。

   * 内置指标模拟器：以 sku 为确定性种子，按时间推进产生 impressions/clicks/conversions 序列；CTR 按品类基线 ± 扰动，标题质量差时扰动偏负（为飞轮制造真实信号）。

   * 暴露 `GET /mock/api/metrics?sku=` 供 collector 拉取，demo 全程无需外网。
3. **指标回流（Collector）**

   * `POST /api/publish`（仅当 task 用户已确认，否则 409）、`GET /api/publish/{job_id}`（状态 + steps）、`POST /api/publish/{job_id}/collect`（拉一次指标落 `data/metrics.jsonl`）。
4. **进化闭环 v2**

   * `evolution.evolve()` 注入第三证据源：metrics anomalies（与 experiences、差评并列）。

   * 典型提案：`low_ctr` → `prompt_patch`：「遇到X类目时，标题前 30 字符必须包含核心关键词」；evidence 引用具体指标行。

   * 人审闸口沿用现有 approve / reject / rollback。
5. **前端闭环**

   * 结果页：「确认上架」按钮 → 上架进度面板流式渲染 `steps[]` → 成功展示 live URL。

   * Admin：数据看板（每 job 指标曲线 + 异常标记）与提案区联动，提案 evidence 中的指标可点击溯源。

## Not-To-Do List

* ❌ 严禁接入真实平台写接口（SP-API / Shopee OpenAPI）——资质周期不可达。

* ❌ 严禁任何形式的模型训练（无 RLHF、无微调）；「强化学习」= 提案机制 + 版本化提示词/规则 + 人审回滚。

* ❌ 严禁无人值守自动上架与自动改写——用户确认是硬闸口。

* ❌ 严禁在真实平台自动点击提交——扩展只回填，提交键属于人。

* ❌ 严禁 Computer Use 真机现场演示——只留接口占位与 flag。

* ❌ 严禁静默上架路径——无 `steps[]`/截图的执行视为黑盒，等同驳回。

