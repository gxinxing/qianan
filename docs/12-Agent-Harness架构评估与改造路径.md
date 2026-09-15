# Agent Harness 架构评估与改造路径

- 日期：2026-09-14
- 触发：用户第一感觉「这个站点太像 pipeline，不像能自主运行的 agent，意图判断、agent 编排都没有」
- 结论：**判断成立**。Agent 性是真的，但只长在叶子节点与内环；**编排层是确定性 pipeline**。

---

## 一、唯一判据

> **下一件事做什么，是代码写的，还是模型在运行时选的。**
> 代码写 → 里面调 100 次 LLM 也是 pipeline。模型选 + 代码只给动作与约束 → agent。

## 二、代码级取证（不是感觉，是证据）

| 判据 | 证据（文件:位置） | 现状 |
|---|---|---|
| 主干顺序 | `orchestrator.py:313` `run_pipeline` | 硬编码：规划→理解→规则→逐平台(文案/视觉/自愈)→策略报告→反思，**无分支** |
| 规划是否改变执行图 | `orchestrator.py:58` `plan_task` + `schemas.py:120` `TaskPlan` | **无**。只输出 `strategy/heal_budget/focus`；`strategy` 只是文本，`heal_budget` 只改自愈轮数上限，`focus` 只注入一句话。**任何取值执行图都一模一样 → 表演式规划** |
| 意图识别 | 全后端 `grep -rn "intent\|router\|classify\|dispatch"` | **0 命中**。`/api/generate` 对所有输入走同一条路 |
| 动作空间对编排层可见 | `agent_core/registry.py` 的消费者 | 只被叶子 `run_tool_loop` 消费；编排层看不到动作表 |
| 任务分解谁做 | `req.platforms`（前端勾选） | 用户选的，不是 agent 分解的。详情图/视频 `run_detail_shots`/`run_video` **无条件全跑** |
| agent 间 handoff | `orchestrator.py:356` `build_one` | agent 只是被 `asyncio.gather` 并发 `await` 的普通函数，**平台之间零通信** |
| 回边 / 重规划 | `orchestrator.py:427` except | 失败 = `task.failed` 或 fallback。不能「发现规则不适用 → 回头重新理解商品」 |
| 自主性长在哪层 | `agent_core/loop.py` `run_tool_loop` | **真 function calling**（轮数/墙钟/兜底齐全），但只用在 `_heal_listing` 自愈循环里 |

**定性**：`run_tool_loop` 已经证明了「带工具的自主循环」在这个代码库里跑得通、
有预算控制、有兜底。**问题是它没被提到编排层。** 把同一个循环抬一层，就是 harness。

## 三、Harness = 一个循环 + 三张表

现有系统已经有循环，缺的是三张表。没有表，模型无从选路。

### 3.1 动作表（Action Registry）— 分四类

| 类别 | 千岸对应动作 |
|---|---|
| **读**（查外部数据） | 查平台规则、查汇率/竞品价、查热搜 |
| **写**（生成/修改产物） | 文案、主图、A+ 详情、详情图、视频 |
| **问**（信息不足反向追问） | 缺图/缺卖点/市场不明确 → 追问用户，**不启动生成** |
| **止**（终止） | `finish` 交付；`publish` 需人审 |

⚠️ **只有函数名不算表。** 每个 `ActionSpec` 必须带：

```python
ActionSpec(
    name="generate_visual",
    kind="agent",            # tool | agent
    isolation="context",     # 是否需要上下文隔离（fork）
    precondition=lambda bb: bb.has("understanding"),
    writes=["listings.*.main_image"],
    cost="expensive",        # 预算表据此扣减
    handler=visual_agent.run,
)
```

**缺了 `precondition` 与 `isolation`，"动作表"就只是个函数名列表。**

### 3.2 黑板（Blackboard）

```python
class Blackboard(BaseModel):
    request: GenerateRequest
    intent: Intent | None = None
    understanding: Understanding | None = None
    rules: dict[str, dict] = {}
    listings: dict[str, PlatformListing] = {}
    open_issues: list[ComplianceIssue] = []
    step: int = 0
    tokens_used: int = 0
    deadline: float = 0.0
    log: list[ActionRecord] = []
```

多 agent 协作**不靠 agent 互相对话，靠黑板交换** —— 这是上下文隔离的前提。

### 3.3 策略与预算（Policy）

- **强制动作的判定优先级必须高于模型决策**：

```python
forced = registry.pending_forced(bb)     # 合规体检 / publish 人审
action = forced[0] if forced else await decide_next(client, bb, registry.available(bb))
```

  这条把「数字只来自工具」「写入必须人审」两条铁律**机制化**，而不是靠 prompt 祈祷。

- **硬上限**：步数 / 墙钟 / token。超限则走 `deterministic_finish(bb)` —— 用现有确定性路径收尾。
  > **关键收益：模型抽风最多退化成今天的 pipeline。下限不变、上限提升** —— 这是能安全上线的前提。

## 四、输入理解三层 / 任务规划三级

| 层 | 现状 | 应做 |
|---|---|---|
| 商品理解 | ✅ 有（`agents/understanding.py` → `Understanding`） | 保持 |
| **意图理解** | ❌ 无 | `goal`(出包/只改文案/只体检/重做某平台/询价) + `platforms` + `missing` + `confidence`，**必须是程序消费的结构化输出** |
| **缺口理解** | ❌ 无 | `missing` 非空且置信度低 → 走 `ask`，不启动生成 |
| L0 无损规划 | ✅ 有 | — |
| **L1 可执行规划** | ❌ 无 | plan 产出 `actions[]` + `skip[]`，**被执行器直接消费** |
| **L2 可重规划** | ❌ 无 | 前提被推翻（规则不适用/识图错/预算尽）→ 回 planner |

## 五、改造路径（增量、非破坏、每步可独立验证）

### Step 1（半天）规划从「填表」变「选路」
- `TaskPlan` 新增 `actions: list[PlannedAction]` + `skip: list[str]`（**新增字段，非破坏**）
- planner 可选工具从 1 个（`submit_plan`）扩到 9 个：`understand_product / match_rules / generate_copy / generate_visual / generate_detail_shots / generate_video / audit_compliance(强制) / heal_copy / reflect_memory(强制)`
- `run_pipeline` 按 `plan.skip` 真跳过阶段
- **验证**：强制 `skip=["generate_video","generate_detail_shots"]`，看耗时是否真降

### Step 2（1–2 天）抽黑板 + 把阶段函数改成 ActionSpec + while 驱动
- 保留 `deterministic_finish(bb)` 作为超预算/异常的确定性收尾
- **验证**：关掉 planner 后动作序列是否恒等（复用现有消融框架）

### Step 3（1 天）加意图层
- `/api/generate` → `/api/agent/run`；保留旧接口为 `goal="full_package"` 的别名（**不破坏契约**）
- **验证**：4 条判据全绿

## 六、怎么证明「真的变了」（评审必问）

| 判据 | 测法 | pipeline 预期 | agent 预期 |
|---|---|---|---|
| 动作序列条件熵 | 同一商品跑 N 次，记录动作序列 | H=0（恒等） | H>0 |
| 输入→路径敏感性 | 构造「图已合规」vs「图需重做」 | 路径相同 | 路径不同 |
| 规划保真度 | 强制 `skip=[generate_video]` | 不生效 | 生效且耗时下降 |
| 重规划次数 | 注入「规则库缺该类目」 | 0 | ≥1 |

> **现成指标**：已有消融实验的「差异化度」（完整管线 0.30 锚点 / 去规划 0.71 失控）。
> 它测的正是**路径多样性**——把它从「文案文本差异」换成「动作序列差异」，就是 agent 化的验收指标。

## 七、多 Agent：什么时候才该 fork（奥卡姆）

**默认不 fork。** 只有出现下列之一才 spawn 子 agent：

| 该 fork | 理由 | 千岸对应 |
|---|---|---|
| 真并行 | 子任务互相独立 | 5 平台并行（现在是对的） |
| 需要独立视角 | reviewer 不能看到 writer 的推理过程，否则会被带着走 | `review_listing` 已是此模式 |
| 上下文隔离 | 子任务产物大，塞回主线会污染上下文 | 视觉素材生成 |

**不该 fork**：串行的、依赖前一步结果的、只是「看起来更像 agent」的。

---

# 附录：Step 1 已落地（2026-09-14）

## 改了什么

| 文件 | 改动 |
|---|---|
| `server/app/schemas.py` | 新增动作空间常量 `OPTIONAL_ACTIONS` / `FORCED_ACTIONS` / `ALL_ACTIONS` / `ACTION_LABELS`；`TaskPlan` 加 `skip`（规划声明）+ `skipped_actions`（实际生效）；`AblationConfig` 加 `force_skip`（验证通道） |
| `server/app/orchestrator.py` | 新增纯函数 `filter_skip_request()`（policy 层：强制动作不可跳过）与 `resolve_skip()`；`plan_task` 的 `submit_plan` 扩出 `skip` 参数 + prompt 说明 + 拒绝留痕；`run_pipeline` 在阶段序列后**消费**规划，"详情图/视频"两个阶段由 `plan.skip` 决定是否进入执行图 |
| `server/app/agents/visual.py` | 修一处会**掩盖跳过效果**的副作用：`run()` 的 mock 分支原先越权预填 `detail_images` / `video_url`（这两个字段本该由 `run_detail_shots` / `run_video` 负责），导致跳过后仍显示有产物（假阴性） |
| `server/tests/test_plan_skip.py` | 新增 6 个纯逻辑测试（policy 过滤 / 脏输入容错 / force 通道覆盖 / 默认值兼容） |
| `web/lib/api.ts`、`web/lib/types.ts` | `TaskPlan` 加 `skip` / `skipped_actions` |
| `web/components/AgentCapabilityPanel.tsx` | ① 自主规划卡片新增「**执行图调整**」证据行：显示本次跳过了哪些步骤（或诚实说明未跳过） |

**未改动**：`/api/generate` 请求/响应契约不变（`AblationConfig.required` 仍为空数组，旧客户端请求体无需改动，已用 OpenAPI 校验）。`_run_pipeline` 的其余阶段顺序、并行度、自愈逻辑全部原样。

## 两级验证（可复现）

### 第一级：mock 模式确定性验证（秒级）

隔离副本 + `QIANAN_MOCK=1`，A/B 对照：

| 组 | `plan.skip`(声明) | `skipped_actions`(生效) | 详情图 | video_url |
|---|---|---|---|---|
| A 对照（不跳过） | `[]` | `[]` | **4 张** | 有 |
| B 实验（force_skip 两个） | `[]` | `['generate_detail_shots','generate_video']` | **0 张** | 无 |

→ 执行器确实消费了跳过项，且对照组未被误伤。

### 第二级：真模式端到端（关键证据）

用真实网关跑单平台（Amazon），同一商品连跑两次：

| 组 | 耗时 | `plan.skip`（模型**自主**声明） | `skipped_actions` | 详情图 | 视频 |
|---|---|---|---|---|---|
| ① 默认 | **193.1s** | `['generate_video']` | `['generate_video']` | 4 张 | 无 |
| ② force 全跳 | **86.3s** | `['generate_video']` | `['generate_detail_shots','generate_video']` | 0 张 | 无 |

**① 组是本次改造最硬的证据**：`decided_by=planner`，模型**自己**决定跳过视频，而且它的 strategy 文本与 skip 决策一致：

> 「针对 Amazon 平台便携榨汁杯，主打轻量化与快充卖点，**跳过视频生成以加快上架，保留详情图展示拆洗结构与材质质感**。」

—— 这说明模型是在**判断**（保留展示结构/材质的详情图、砍掉对这个小工具价值最低的视频），不是随机输出。

**耗时下降 55.3%（193.1s → 86.3s）**，证明"跳过"不是写进日志的文本，而是真的从执行图里移除了阶段。

### 声明 vs 生效：两个字段的语义分离被真实运行验证

② 组的 `plan.skip` 仍是模型原话 `['generate_video']`，而 `skipped_actions` 是 `['generate_detail_shots','generate_video']`（force 通道覆盖）。**两个字段对照即可区分"模型想干什么"与"实际执行了什么"** —— 这是后续接 policy 审计的接口。

### 留痕样例（真实运行）

```
[plan/submit_plan]  1 平台 | 策略=…跳过视频生成以加快上架… · heal_budget=1 · 跳过=展示视频
[plan/skip_actions] 展示视频 | 已从执行图移除，本任务不再执行这些步骤
```

## 回归

- `pytest tests/`：**16 passed**（原 10 + 新增 6），0.37s
- `tsc --noEmit`：0 error
- OpenAPI 契约：`AblationConfig.required = []`，新增字段全可选
- **用户数据零污染**：验证全程在 `/tmp/qianan-step1-qa` 隔离副本内进行，`server/data/` 的 69 个任务 / 50 条记忆未被写入

## 下一步（Step 2 的前置已就绪）

Step 1 验证了一个关键前提：**执行器能被规划驱动**。Step 2 只需把 `run_pipeline` 的线性阶段函数改造成 `ActionSpec` 注册表，用 `while` 循环替代硬编码顺序，`plan.skip` / `pending_forced` 的消费点已经在位（`resolve_skip` 即 policy 层的雏形）。

---

# 附录：意图层最小切片已落地（2026-09-14，即原 Step 3 的 1/3）

> 背景：演示视频提前到明天，先做「输入理解第②层」——它直接回应「意图判断都没有」这条质疑，且见效最快。

## 设计：意图先划动作空间，规划再在空间内选路

```
用户诉求文本 ──► ① 意图判定 ──► 动作空间（本次允许的动作集合）
                     │                    │
                     │                    ▼
                     └──────────► ② 规划（在空间内选路 / 跳过可选动作）
                                          │
                                          ▼
                                    ③ 执行器（两条来源分别消费）
```

- **两个 goal**：`full_package`（默认，全量动作）/ `preview`（只做「读懂商品 + 匹配规则」，产出策略报告，不生成物料）
- **不产出上架包 ⇒ 无需合规体检**：guardrail 保护的是「要上架的产物」，不是流程本身。这一点在结果页显式写明，避免被理解成「为了演示把闸门关了」。
- **`platforms` 从自然语言抽取**：卖家说「只铺 Shopee 和 Lazada」→ 覆盖请求里勾选的 5 个平台。**意图不只选模式，还能改写请求参数。**
- **未写诉求时一次模型都不调**（`decided_by=default`）→ 绝大多数既有请求的延迟与成本零变化。
- **兜底铁律**：判定失败（网关挂 / 输出非 JSON / 未知 goal）一律回退 `full_package`，**绝不静默降级到更少的产出**。已由纯逻辑测试锁死。

## 改了什么

| 文件 | 改动 |
|---|---|
| `server/app/schemas.py` | 新增 `GOAL_*` / `GOAL_LABELS` / `GOAL_ACTIONS` / `actions_for_goal()`；新增 `Intent` 模型（goal / platforms / summary / confidence / decided_by / excluded_actions）；`GenerateRequest.request_text`；`TaskRecord.intent` |
| `server/app/agents/intent.py`（新） | `IntentAgent` + `describe()`：一次 `chat` 调用 + JSON 提取 + 平台白名单校验；未写诉求短路、异常兜底 |
| `server/app/orchestrator.py` | `resolve_skip(plan, ablation, allowed)` 增加动作空间裁剪（**意图排除 ≠ 规划跳过**，两者证据分开）；新增 `excluded_actions(goal)`；`run_pipeline` 在规划**之前**插入意图判定、诉求指定平台时覆盖 `req.platforms`、新增 `preview` 早退分支；两处留痕（`understand_intent` / `exclude_actions`） |
| `server/tests/test_intent.py`（新） | 7 个纯逻辑测试（动作空间分区 / 证据字段 / 空间裁剪 / 不调模型 / 解析与白名单 / 三类兜底 / 向后兼容） |
| `web/app/page.tsx` | 新增「你想让我做什么」输入框 + 3 个快捷短语（出完整包 / 先看方案 / 只要东南亚）；提交按钮按是否有诉求改文案 |
| `web/app/(app)/result/TaskResultClient.tsx` | 新增 `preview` 专用结果页分支（意图复述 + 本次执行图「已执行 / 不执行」对照 + 策略报告 + 下一步 CTA），**不改动原有结果页逻辑** |
| `web/lib/api.ts` | `Intent` 类型、`GenerateInput.request_text`、`TaskDetail.intent` |

## 真模式端到端验证（同一商品，只换一句话）

| 组 | 诉求文本 | 判定 goal | 判定者 | 实际平台 | 产物 | 耗时 |
|---|---|---|---|---|---|---|
| A | （留空） | `full_package` | `default`（**未调模型**） | amazon | 1 个上架包 + 策略报告 1319 字 | 173.5s |
| B | 先别生成，我想看看你打算怎么做 | **`preview`** | `planner`（置信度 **0.98**） | — | **0 个上架包** + 策略报告 1343 字 | **28.2s** |
| C | 只铺 Shopee 和 Lazada（请求传了 5 平台） | `full_package` | `planner`（0.95） | **shopee, lazada** | **2 个上架包** | 181.5s |

**三条判决全部成立：**
1. **意图判断**：同一商品、只换一句话，`goal` 从 `full_package` 分叉到 `preview`
2. **意图改变执行图**：`preview` 产出 0 个上架包 + 一份策略报告，排除 6 个动作
3. **意图改写请求参数**：请求传 5 个平台，模型从自然语言里抽出 2 个，实际只生成 2 个包

**B 组省时 83.7%（173.5s → 28.2s）** —— 因为按意图跳过了全部生成。模型自己的复述是：

> 「卖家希望先查看便携榨汁杯的上架方案，暂时不要生成上架包」——与 `goal=preview` 完全一致，说明是理解而非关键词匹配。

### 留痕样例（真实运行）

```
[plan/understand_intent] 先别生成，我想看看你打算怎么做 → 先出方案，暂不生成 · 置信度 0.98
[plan/exclude_actions]   多语言文案、规范主图、合规体检、反思回写记忆、多角度详情图、展示视频
                         → 本次意图「先出方案，暂不生成」不包含这些步骤
```

```
[plan/understand_intent] 只铺 Shopee 和 Lazada → 出完整上架包 · 仅 2 个平台（诉求中指定） · 置信度 0.95
```

## 回归

- `pytest tests/`：**23 passed**（Step 1 的 16 + 本轮 7）
- `ruff check`（本轮改动文件 + `tests/`）：**All checks passed**
- `tsc --noEmit`：**0 error**
- `GenerateRequest.request_text` / `TaskRecord.intent` 均为可选新增，**旧客户端请求体无需改动**
- **用户数据零污染**：全程在 `/tmp/qianan-step3-qa` 隔离副本跑，`server/data/` 的 69 个任务 / 50 条记忆未变动

## 边界与诚实记录

- 输入理解只做了第②层（**意图**），第③层**缺口理解**（信息够不够 → 该不该追问）仍未做。
- `copy_only` 等 goal 的候选**本轮主动放弃**：它会引发「无主图 → 合规体检报 mainImage error → 演示看起来像失败」的连锁问题，不做无准备的扩展。
- 平台抽取依赖模型理解，未做正则兜底；若模型抽错，卖家仍可在请求里显式勾选覆盖（勾选是主字段，诉求文本只做覆盖、不取代）。


