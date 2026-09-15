# 多 Agent 蜂群架构（主控 + 执行 agent）

日期：2026-09-15 凌晨
产物：`qianan/server/app/agents/swarm/`
启用：`QIANAN_SWARM=1`（**默认关闭**）

---

## 一、结构：1 主控 + 2 类执行 agent

```
                    ┌─────────────────────────┐
                    │  Supervisor（主控）      │
                    │  看黑板 → 选一个动作     │
                    │  不生成任何内容          │
                    └───────────┬─────────────┘
                                │ 派活（只传参数，不传推理）
              ┌─────────────────┼─────────────────┐
              ▼                 ▼                 ▼
     PlatformWorker      PlatformWorker     ReviewWorker
      (amazon)            (shopee)          （上下文隔离）
      文案 + 视觉          文案 + 视觉        只报告问题、不改文案
              │                 │                 │
              └──────── 写回 ───┴─────────────────┘
                             ▼
                    Blackboard（持久化黑板）
                    版本号 / 动作历史 / 前置条件
```

**奥卡姆剃刀**：只保留 1 个主控 + 2 类 worker，不堆"角色 Agent"。
多 Agent 的价值只来自三件事 —— 真并行、独立视角、上下文隔离；其余都是装饰。

| 文件 | 职责 |
|---|---|
| `blackboard.py` | 共享状态 + 动作规格（`ActionSpec`）。版本号驱动的审核失效 |
| `supervisor.py` | 主控：动作表 + 前置条件守卫 + 确定性兜底 |
| `platform_worker.py` | 执行：单平台文案与视觉闭环，写回黑板 |
| `review_worker.py` | 执行：独立审核（规则引擎 + 语义），**不看写作者推理** |
| `__init__.py` | `run_swarm` 入口，把结果写回 task 与 trace |

---

## 二、四个关键机制

### 2.1 审核失效：用版本号，不用手工维护的集合

旧实现靠一个 `reviewed: set[str]` 手工增删，漏删一次就会出现「改过文案仍宣称已审核」。
新实现用**版本号对齐**：

```python
@property
def review_valid(self) -> bool:
    return self.has_copy and self.review_version == self.copy_version
```

`mark_copy()` 让 `copy_version + 1`，两者一旦不等，审核结论**自动作废**，结构上不可能出错。
改完文案后 `submit_deliverable` 会立刻被 `all.review.valid` 阻塞。

### 2.2 前置条件：模型选择，代码判定

每个 `ActionSpec` 带 `preconditions`，执行前由代码检查：

```python
blocked = spec.blocked_by(bb)
if blocked:
    return f"无法执行 {spec.name}：前置条件不满足 —— {'、'.join(blocked)}。请换一个当前能做的动作。"
```

被拒的原因**原样回给模型**，它据此换动作。这就是「模型负责选择下一步，代码负责判定这一步是否允许执行」。

### 2.3 上下文隔离：主控的观察里没有 worker 的推理

`Blackboard.observe()` 只返回结构化状态（版本号、阶段、阻断数、动作历史），
**刻意不包含任何 worker 的中间推理或 prompt**。reviewer 因此不会被"写作者本来想表达什么"带着走。

### 2.4 降级：最差是一条流水线，不会更差

模型抽风 / 超轮数 / 网关异常 → `deterministic_finish()` 用确定性路径补齐必备步骤
（理解 → 文案 → 审核 → 修订重审），**不补图片视频**（加分项且耗时）。
未完成则置 `partial`，绝不静默升级为 `done`。

---

## 三、证据：怎么证明它是 agent 而不是 pipeline

### 3.1 路径敏感性（决定性证据）

同一任务（2 平台），**只改模型的动作选择**：

| 脚本 | 实际动作序列 |
|---|---|
| A 先文案后出图 | `understand → copy ×2 → review`（4 步）|
| B 先出图后文案 | `understand → images → copy`（3 步）|

硬编码流水线的动作序列恒定；这里不同选择在运行时产生了不同路径。

### 3.2 违规被守卫拒绝

模型第一步就要求交付：

```
[guard] submit_deliverable  ok=False
        note=前置条件不满足: ['all.copy.ready', 'all.review.valid']
最终黑板状态: partial        ← 不会因为模型要求交付就变成 completed
```

### 3.3 端到端

`QIANAN_SWARM=1 QIANAN_MOCK=1` 下跑 2 平台：HTTP 200、`status: "done"`、
`已完成 2 个平台的上架包，全部通过审核`，trace 含 `swarm_init`。

### 3.4 测试

`pytest` **49 passed**（40 → 49，新增 9 个蜂群测试）· `ruff app/agents/swarm/` **All checks passed**

---

## 四、如何启用

```bash
QIANAN_SWARM=1 .venv/bin/python -m uvicorn app.main:app --port 8001
```

**默认关闭**，走原来的 `run_chat_agent` 工具循环 —— 演示路径零风险。

---

## 五、诚实清单

### 5.1 已知限制

| 限制 | 说明 |
|---|---|
| **mock 模式下看不出蜂群** | mock client 的 `chat_with_tools` 不返回 `tool_calls`，循环立即收敛，走的是 `deterministic_finish` 兜底。**只有真实模式才能看到模型自主选路**。 |
| 蜂群未接多轮会话 | 仍是「一条消息一个任务」，P0-1（会话历史与状态继承）未解决 |
| 黑板未落盘 | `Blackboard.snapshot()` 已就绪，但还没接进 task_store，断线仍无法恢复 |
| 无 `waiting_user` | 信息不足时不会主动追问（验收标准 1 未落地） |
| 平台 worker 串行 | 目前主控逐个派活，未做 5 平台 `asyncio.gather` 并行 |

### 5.2 与审计目标架构的差距

审计第 4 层建议「先保留一个主控，加两类隔离 worker」—— **本轮已落地**。
但审计同时强调「**多 Agent 不是完整性的关键；状态、约束、恢复与评测才是**」：
状态（黑板）、约束（前置条件 + 交付闸门）已做；**恢复（断线重连、失败重试）与评测（路径敏感性统计）未做**。

### 5.3 我自己 review 出的两处疏漏（已修）

1. `Supervisor.run` 调 `run_tool_loop` 时**漏传 `should_stop`** → 蜂群模式下取消失效。已补，并加了 `cancelled` 分支。
2. `bb.rules[platform]` 用 `bool()` 判定 → 合法的空规则 dict 会被误判为"规则未就绪"。改用 `platform in self.rules`。
