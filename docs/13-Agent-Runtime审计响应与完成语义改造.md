# Agent Runtime 审计响应 · 第 1 层「完成真实性」落地记录

日期：2026-09-15 凌晨
触发：外部审计结论「组件层 Agent 化，产品闭环仍是 Pipeline，成熟度 45/100」
范围：**只落地第 1 层**。第 2–4 层（Agent Runtime / 多轮恢复 / 多 Agent）写为规划，不盲动。

---

## 一、审计结论复核：对齐、加深、修正

审计给的行号我逐条读过代码。**结论属实**，其中三处我做了加深，另发现三个审计未列出的问题。

### 1.1 属实且属核心（P0）

| 审计条目 | 我的复核 | 加深/修正 |
|---|---|---|
| `submit_deliverable` 无硬交付条件 | 属实。`tool_deliver` 唯一硬条件是 `listings` 非空；`summary` 里 `len(listings)` 用的是**实际生成的平台**而非 `req.platforms`，所以「勾 5 个只做出 2 个」会显示「已为 2 个平台生成**完整**上架包」 | —— |
| 超时/超轮数仍标 `done` | 属实。收尾是 `if task.status != TaskStatus.done: task.status = TaskStatus.done`，**完全不看 `result["fallback"]`** | 补充：还有第三种情况——循环自然收敛但**没调 `submit_deliverable`**，此前也算 done |
| 停止按钮只断前端 | 属实。`run_tool_loop` 没有任何取消检查点 | —— |
| `/api/chat` 绕过鉴权 | 属实。`create_task(gen_req, owner_uid="anonymous")` 写死 | 补充：后果不只是"绕过鉴权"，而是**所有访客的任务混在同一租户下互相可见**——演示时多评委同时用会看到彼此的数据 |

### 1.2 审计低估的一条

**P1「SSE 全量快照 type 撞名」—— 不是"兼容分支不可达"，是数据被冲掉。**

前端 `useChat.ts:175`：

```js
if (data.type === "listing") {          // 无条件匹配 + continue
  listings: [{ platform: data.platform, ... }]   // 全量快照没有 platform → undefined
  status: "running"                              // 真实 status 被硬编码覆盖
  plan: null                                     // plan 被清空
}
```

全量快照每 3 秒推一次，每次都会用**一条 `platform: undefined` 的假记录**覆盖右侧面板里已生成好的多平台产物。这是**数据丢失型 bug**，演示时右侧面板会不停闪回。

### 1.3 审计未列出、本轮发现并修复的三个

| # | 问题 | 证据 | 影响 |
|---|---|---|---|
| N1 | **枚举序列化错误**：`str(TaskStatus.done)` 在 Python 3.10 得到 `"TaskStatus.done"` 而非 `"done"` | 实测 SSE 输出 `"status": "TaskStatus.done"` | 前端 `status === "done"` **永远判不中**，所有状态判断失效 |
| N2 | **无条件兜底 `done`**：`main.py:637` 不管 Agent 是否已推过都再推一次 | 实测一次请求收到 2 个 `done`，第二个无 `summary` | 第二个覆盖第一个，UI 上的完成文案丢失 |
| N3 | **`partial` 不持久化**：`persist_task` 只在 `status == done` 时调用 | `main.py:641` | 部分完成的产物一断线就彻底丢失，"可恢复"无从谈起（N3 是本轮引入 `partial` 状态后暴露的） |

---

## 二、第 1 层落地内容

### 2.1 交付闸门：把「完成」的判定从提示词挪进代码

新增纯函数 `chat_app.chat_agent.evaluate_delivery_gate(platforms, listings, reviewed)`，四条不变量：

1. **请求平台全覆盖** —— `req.platforms` 逐个检查，未生成的直接 blocker
2. **必需产物完整** —— 标题 / 五点描述 / 主图，缺一即不可上架
3. **阻断级 error 为零** —— 口径为 `severity == "error" and field not in IMAGE_ONLY_FIELDS`
4. **审核覆盖且仍然有效** —— `reviewed` 集合在 revise 后会被清除，因此这条同时覆盖「审核后又被改过」

`tool_deliver` 改为：**闸门不通过就不置 `done`**，把缺口原样回给模型让它继续做，并在 trace 里留 `delivery_gate / 拒绝 finish`。

**为什么排除 `mainImage`**：这类问题模型无论修订多少轮都修不掉，若纳入闸门会让它反复 `revise_listing` 直到超轮数，把 5 分钟预算烧光。改由「缺主图」这一条覆盖 —— 有图放行，无图拦住。口径与 `tool_revise` 保持一致，避免两者打架造成死循环。

### 2.2 fallback / 取消 不再标成功

`TaskStatus` 新增 `partial` / `cancelled`。收尾判定改为：

| 情况 | 状态 | 说明 |
|---|---|---|
| 闸门放行 | `done` | 唯一能置 done 的路径 |
| `result["cancelled"]` 或 `should_stop()` | `cancelled` | 已生成的内容保留 |
| `fallback=True` 且有产物 | `partial` | 如实告知 N/M 平台，未达交付标准 |
| `fallback=True` 且无产物 | `failed` | |
| 收敛但没调 `submit_deliverable` | `partial` | 产物未经闸门校验，不算完成 |

### 2.3 审核失效

`tool_revise` 复检后按结果更新 `reviewed`：仍有 error 则 `discard`，否则 `add`。此前修订后审核状态仍算有效。

### 2.4 真取消

- `run_tool_loop` 新增 `should_stop`，在**每轮开头**和**每个工具执行前**检查（单个图像/视频生成就可能几十秒，逐个检查才停得及时）
- `main.py` 新增 `POST /api/chat/{task_id}/cancel` + 进程内 `_CHAT_CANCELLED` 集合
- 前端 `handleStop` 在 abort 之外**额外调用取消端点**；`taskIdRef` 从 `init` 事件取 task_id

### 2.5 协议与鉴权

- `_listing_snapshot` 的 `type` 改为 `listing_full`（前端该分支**已实现**，故前端零改动即可落位）
- 所有 SSE `status` 改用 `task.status.value`
- 兜底 `done` 改为「Agent 没推过才推」
- `persist_task` 条件扩展为 `done / partial / cancelled`
- `/api/chat` 接入 `Depends(cbauth.require_user)` + `cbauth.uid_of(user)`，与 `/api/generate` 一致

**接入鉴权的安全性已验证**：`REQUIRE_AUTH=false` 时 `require_user` 不抛错，匿名请求得到基于 IP+UA 派生的独立租户（`anon_<12位hex>`）。所以线上演示（未开鉴权）不会挂，同时多评委之间数据隔离。

### 2.6 Mock 与真实共用完成标准

`chat_agent` 的 mock 分支跑完 `run_pipeline` 后，也过一次同一道闸门，不达标就置 `partial`。此前 mock 直接 `on_event("done")` 且完全绕过工具循环，导致「演示时看到的完成」和「真实运行的完成」不是同一套判定。

---

## 三、验证结果

| 检查 | 结果 |
|---|---|
| `pytest tests/` | **40 passed**（23 → 40，新增 17） |
| `ruff` 改动文件 | 通过（余下 `E402`/`F821 ALL_PLATFORMS` 为存量） |
| `tsc --noEmit` | **0 error** |
| SSE `done` 事件数 | 2 → **1** |
| SSE `listing` 事件数 | → **0**（`listing_full` 正常） |
| SSE `status` 值 | `"TaskStatus.done"` → **`"done"`** |
| `/api/chat` 不带 token | **HTTP 200**（鉴权接入未破坏演示路径） |
| 租户隔离 | `owner_uid = anon_8706ee88bbbd`（指纹派生，非 `anonymous`） |
| 取消端点 | `{"ok":true,"cancelled":true}` |
| 你的 `data/` | **零污染**（全程 `/tmp` 隔离副本） |

---

## 四、诚实清单：本轮没做的

### 4.1 已落地的验收标准（审计 10 条）

✅ 3 模型提前 finish 被 policy 拒绝 · ✅ 4 工具超时不显示完成 · ✅ 5 点击取消后台停止 · ✅ 6 审核后修改使审核失效

### 4.2 未落地（分属第 2–4 层）

| 验收标准 | 归属 | 为什么这轮不做 |
|---|---|---|
| 1 信息不足时追问且不开始昂贵生成 | 第 2/3 层 | 需要 `waiting_user` 状态机 + 缺口理解，不是加个判断就能成立 |
| 2 同一会话第二句修改上一轮产物 | 第 3 层 | 需 SKU Project 持久化与会话-项目绑定，改动面覆盖 task_store |
| 7 平台失败单独重规划 + partial 交付 | 第 2 层 | 需 ActionSpec 的 precondition 与黑板 |
| 8 新技能工具进入 Chat Agent 动作空间 | 第 2 层 | 需把 `ToolSpec` 扩成 `ActionSpec` 并接 skill_store |
| 9 Mock 与真实产生同类型动作轨迹 | 第 2 层 | **见下方风险说明** |
| 10 统计路径敏感性等 5 项指标 | 第 2 层后 | 需先有稳定动作轨迹 |

### 4.3 两个必须说清的风险

**① mock 模式下的取消无效。** `should_stop` 只贯穿 `run_tool_loop`，而 mock 分支直接 `await run_pipeline`，`run_pipeline` 不检查取消信号。真实模式（非 mock）取消有效。要让 mock 也可取消，得给 `run_pipeline` 也加检查点。

**② 我没有把 mock 改成走工具循环。** 审计 P1 建议「Mock 与真实模式共用同一编排」，我**只统一了完成标准，没统一编排路径**。原因：mock client 的 `chat_with_tools` 能否产出合理的 `tool_calls` 未经验证，贸然切换等于拿明天要用的演示路径做实验。这条路需要单独的验证时间。

---

## 五、第 2–4 层规划（沿用审计目标架构）

```
Conversation / SKU Project → 持久化 Blackboard → Policy 硬约束
   → Planner 选一个可执行 Action → 执行 → Observation → Checkpoint
   → 完成 / 追问用户 / 等待审批 / 重规划 / 部分失败
```

| 层 | 内容 | 估时 | 本轮已完成的前置 |
|---|---|---|---|
| 2 | `ToolSpec` → `ActionSpec`（preconditions / writes / invalidates / cost / idempotency_key / approval）+ 持久化 Blackboard + 「一轮一个动作」循环 | 2–3 天 | `evaluate_delivery_gate` 已是 policy 层雏形；`resolve_skip` 已证明执行器可被规划驱动 |
| 3 | SKU Project 持久化、多轮改单个平台、`last_event_id` 断线重连、`waiting_user` / `waiting_approval` | 2–3 天 | `partial` / `cancelled` 状态已存在，`persist_task` 已覆盖 |
| 4 | 平台生成 worker 并行 + 独立 reviewer（不共享 writer 推理） | — | `asyncio.gather` 与 `review_listing` 已是此模式的雏形 |

**核心原则（本轮已在第 1 层贯彻）**：模型负责选择下一步，代码负责判定这一步是否允许执行。
