# 09 · Agentic 能力说明（评审对照版）

> 目的：把"自主规划 / 工具调用 / 长期记忆 / 反思迭代"四项核心 Agentic 能力，
> 逐条对应到千岸的真实实现、代码位置、前端可见证据与演示动线。
> 所有证据均为运行时留痕，非演示脚本。

---

## 一、总览：为什么千岸是 Agent，不是流水线

千岸的主链路是「规划 Agent 先调研再决策 → 各平台子任务并行执行 → 合规自愈工具循环 → 评审 Agent 反思回写」。
每一步的决策都由模型通过 **真实 function calling** 做出，并留痕到 `task.trace` 与结构化字段（`task.plan` / `task.memory_recall` / `task.reflections`）。

结果页的 **Agent 能力证据面板**（`AgentCapabilityPanel`）把四项能力渲染为可判读的证据卡，评委无需读代码即可逐条核对。

---

## 二、四项能力逐条对照

### ① 自主规划（Planning）

| 维度 | 说明 |
|---|---|
| 实现 | `orchestrator.plan_task()`：模型在制定策略**之前**，可自主调用调研工具（欧盟 GPSR 准入核查 / 竞品价格带 / 平台热搜），再通过 `submit_plan` 工具提交策略、自愈预算（heal_budget）、生成要点（focus） |
| 代码 | `server/app/orchestrator.py` · `agent_core/loop.py` |
| 结构化证据 | `task.plan = {strategy, heal_budget, focus, research_tools[], decided_by}` |
| 前端可见 | 能力面板第 1 栏：决策来源徽章（模型自主决策 / 回退默认）+ "决策前自主调研"工具链 + 策略正文 |
| 兜底 | mock / 网关异常 / 未提交 → 回退默认计划并在面板标注 `fallback`，演示不断档 |

**评委可验证点**：`research_tools` 列表证明规划是"先调研后决策"；换一个商品重跑，策略与 heal_budget 会随之不同。

### ② 工具调用（Tool Use）

| 维度 | 说明 |
|---|---|
| 实现 | `agent_core/loop.py` 通用工具循环：OpenAI function calling 协议，模型决定调什么工具、循环执行直到收敛，带轮数上限与墙钟预算；单工具失败不炸循环，异常整体回退确定性路径 |
| 工具集 | 规划期：`submit_plan` + 已安装技能工具（GPSR 核查 / 竞品价格带 / 热搜趋势）；自愈期：`revise_copy`（修订+自动复检）/ `finish` |
| 代码 | `agent_core/registry.py`（ToolSpec 声明）· `skill_store.py`（技能即工具） |
| 前端可见 | 能力面板第 2 栏：总调用次数 + 按工具聚合的调用清单；右侧轨迹面板逐条实时滚动（含参数与结果摘要） |

**评委可验证点**：轨迹面板是实时日志流（生成中即可观看），不是事后编排的静态文案。

### ③ 长期记忆（Memory）

| 维度 | 说明 |
|---|---|
| 实现 | `memory_store`（JSONL 持久化）：反思 Agent 蒸馏的教训按 `平台+类目` 标签存储；每次生成前 `recall()` 结构化检索 top-3 注入文案提示词，命中后 `mark_hit()` 回写命中次数 |
| 代码 | `server/app/memory_store.py` · 注入点 `orchestrator.build_one()` |
| 结构化证据 | `task.memory_recall = [{lesson, platform, hit_count, source_task}]` |
| 前端可见 | 能力面板第 3 栏：本次召回条数 + 每条教训的**历史复用次数**（当前库内最高单条 80+ 次）；/agent 页有完整记忆库 |
| 演示动线 | 提交同类目第二个商品 → 面板显示"召回 N 条历史教训"→ 教训内容与前一次任务的反思产出对应 → 证明跨任务学习闭环 |

**评委可验证点**：`hit_count` 是跨任务累计的真实计数；`data/memory/experiences.jsonl` 可直接查看原始积累。

### ④ 反思迭代（Reflection & Self-Heal）

| 维度 | 说明 |
|---|---|
| 迭代内环 | 合规体检发现 error 级问题 → 模型在工具循环中自主决定 `revise_copy`（修订并自动复检）或 `finish`，受规划的 heal_budget 与 40s 墙钟双约束；修订解决不了的问题（如主图规格）不入回路 |
| 迭代外环 | 任务完成后评审 Agent（`agents/reflection.py`）对比"商品事实档案 vs 最终文案"，蒸馏可复用教训写入记忆库；忠于事实且合规干净时保持沉默，不往记忆掺水 |
| 代码 | `orchestrator._heal_listing()` · `agents/reflection.py` |
| 结构化证据 | `task.reflections = [{platform, lesson}]` + 各 listing 的 `revised_count` |
| 前端可见 | 能力面板第 4 栏：自愈轮数、合规终态通过率、本次蒸馏的新教训（标注"已回写记忆库"） |

**评委可验证点**：第 3 栏的历史教训正是历次任务第 4 栏蒸馏产出的积累——外环闭环在同一屏幕上自我印证。

---

## 三、与 Anthropic commerce-agents 蓝图的对照

2026-09-02 Anthropic 发布 `anthropics/commerce-agents`（Apache-2.0 参考实现）。其公式：
**Model + Skills + Tools + Memory + UI + Guardrails + Evals**。千岸的对应关系：

| 蓝图概念 | 千岸实现 | 状态 |
|---|---|---|
| Model + Agent loop | `agent_core/loop.py` 通用工具循环（轮数+墙钟双熔断） | ✅ 等价 |
| Skills | `skill_store` 技能商店：规则补丁 + 新工具，安装即增强规划与合规 | ✅ 等价 |
| Tools | 规划期调研工具 + 自愈期修订工具 | ✅ 等价 |
| Memory | 平台×类目结构化记忆 + 命中计数（向量检索为预留升级） | ✅ 等价（结构化检索） |
| UI-as-tools | 结果页消费 `task.plan/trace/memory_recall/reflections` 结构化证据 | ✅ 思路一致 |
| Guardrails | maker-checker：发布（write）必须人审 approved；合规规则引擎在生成与编辑两态执行；文案被约束为"只陈述事实档案有的属性" | ✅ 等价 |
| **Evals** | 暂无独立评测集 | ⚠️ 差距 → 见第五节 |

蓝图最值得抄的三条工程决策，千岸已内建或对齐：
1. **数字只来自工具，不来自模型文本** —— 千岸的合规规则引擎（非 LLM）承担字符上限/禁用词/属性校验，模型只写文案不判合规。
2. **写入必须人审（maker-checker）** —— `POST /api/publish` 要求 `approved=true`，上架执行全程截图留痕。
3. **快照式评测优于多轮模拟** —— 构造中间状态直接断言，见下节规划。

---

## 四、演示动线（3 分钟版本）

1. **首页**：一张随手拍商品图提交（只传图、不填卖点）→ VL 看图识别。
2. **生成中**：右侧轨迹面板实时滚动 —— 规划期调研工具调用 → `submit_plan` → 各平台并行。
3. **结果页首屏**：Agent 能力证据面板四栏（本页核心新增）。
4. **指向第 3 栏**："这条教训被复用 80+ 次，来自之前任务的反思" → 切到 /agent 页看记忆库全量。
5. **编辑文案** → 即时合规校验（Guardrails 在编辑态仍生效）→ 一键上架 → 后台回执截图。

---

## 五、已知差距与下一步

| 差距 | 说明 | 优先级 |
|---|---|---|
| Evals | 缺独立评测集：应把合规规则、历史事故（如"材质未知不得宣称食品级"）编码为可反复跑的快照测试 | 高（决赛前） |
| 记忆检索 | 标签过滤 + 频次排序，无语义检索；教训量大后召回精度会衰减 | 中 |
| 规划深度 | 单轮策略提交，非动态 DAG 重规划；流程异常时不能改道 | 中 |
