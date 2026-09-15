# 千岸 QianAn — 决赛交付清单（2026-09-15 收口）

> 一稿多岸的跨境上新 Agent：1 张商品图 + 一段中文卖点 → 30 秒生成 Amazon / Shopee / 速卖通 / Lazada / TikTok Shop 5 平台合规上架包。

## 一、交付物总览

| 交付物 | 状态 | 位置 / 链接 |
|---|---|---|
| 源代码仓库 | ✅ 已推送 `main` | https://github.com/gxinxing/qianan （HEAD `main`） |
| 公网 Demo（前端） | ✅ 已部署，HTTP 200 | https://ai-native-d5gfb0dm2a28d1fe9-1419921079.tcloudbaseapp.com |
| 公网 API | ✅ 真实模式在线（mock:false） | https://ai-native-d5gfb0dm2a28d1fe9-1419921079.ap-shanghai.app.tcloudbase.com/api |
| 技术说明文档 | ✅ | `submission/SimonStudio_千岸QianAn_复赛作品.docx` + `docs/`（01–14） |
| Agent 闭环验收测试 | ✅ 56 passed（含 4 条端到端） | `qianan/server/tests/test_agent_loop.py` |
| 演示视频 | 🚧 待本机录屏 | 访问上方公网 Demo 录制即可 |

## 二、本次收口修复（评委最易击穿的 4 个 P0）

### P0 #1 修复"假完成"
- `evaluate_delivery_gate()` 四不变量：目标平台全覆盖 / 必需产物完整 / 阻断 error 为零 / 审核覆盖且有效。
- `submit_deliverable` 为**唯一**能置 `done` 的入口；闸门不通过则拒绝并把缺口回给模型。
- 工具循环超时 / 超轮数 / 网关异常 / 取消 → `partial` / `failed` / `cancelled`，**绝不标 done**。

### P0 #2 修 SSE 产物面板
- 后端统一三类事件：`listing_update`（单平台，合并进快照）/ `listing_full`（全量，整块替换）/ `done`（完成）。
- 前端 `web/hooks/useChat.ts` 曾只匹配旧事件名 `listing`，单平台 `listing_update` 被静默丢弃——已修复为合并进快照，右侧面板不再丢状态；并删除死代码、防跨任务串台。

### P0 #3 保护公开 Demo
- `/api/chat` 接 `require_user` + `uid_of`（游客按 IP+UA 派生独立 uid，不再全员互见）+ `check_rate_limit`（与 `/api/generate` 同策略）。
- 前端文案改为"一个会话 = 一次上新任务"（空状态 / 输入框占位 / 底栏提示三处）；多轮会话本期不做。

### P0 #4 增加 4 条 Agent 验收测试
- `server/tests/test_agent_loop.py` **端到端驱动 `run_chat_agent` 主循环**（非只测纯函数），覆盖：
  1. 模型提前提交 → 被拒，status≠done；
  2. 工具循环超限 → 不显示成功（fallback→partial/failed，done 事件 status≠"done"）；
  3. 某平台未审核 → 不能交付；
  4. 全部平台审核通过 → 才 complete（status=done）。

### 决赛当日审计二次整改（2026-09-15 二次收口）

基于静态审计发现，补掉 3 个演示路径上的确定性故障 + 校准文档口径：

- **流水线交付闸门（审计 #3，最致命）**：`orchestrator.run_pipeline` 此前在视觉生成失败（被捕获并续跑）后仍直接置 `TaskStatus.done`，缺主图/仍有阻断级问题也会显示"完成"。现已在置 done 前调用 `evaluate_delivery_gate`：不过闸一律降为 `partial`，并写明未过原因。对话路径与流水线路径现在**同一套闸门口径**。
- **批量接口 NameError（审计 #4）**：`main.py:355` 引用模块作用域未导入的 `ALL_PLATFORMS`（仅 `generate()` 内局部导入），批量请求带 `platforms` 时 `NameError` 直接 500。已将 `ALL_PLATFORMS` 提到底层 `schemas` 导入。
- **聊天面板闪现后消失（审计 #2）**：`chat_agent` 只在交付时把内部 `state["listings"]` 同步进 `task.listings`，而周期全量快照读 `task.listings`——生成中途快照为空，前端 `listing_full` 整块替换把实时产物冲掉。现已在生成/修订后立即同步；前端 `useChat.ts` 的 `listing_full` 也加防御（空快照不再冲掉已渲染产物）。
- **文档口径校准（审计 #5）**：
  - 图像模型：实际经 **TokenDance 网关**调用 Seedream-5.0-lite，并非直接走百炼 Wanx；README 技术栈已更正。
  - 数据留存：任务产物持久化于服务端（非处理即弃），已如实写明。
  - "~90 秒 / 100% 合规"：限定为**已有测试样本下的实测值**，非普遍保证。
  - 多 Agent 蜂群默认关闭（`QIANAN_SWARM=1` 才开），演示范围已限定。

> 新增测试锁定上述修复：`test_pipeline_gate.py`（缺主图→partial / 有主图→done 两条端到端）、`test_batch.py`（批量接口不再 NameError）。后端测试总数 **56 passed**。

## 三、公网冒烟证据（2026-09-15 部署后）

```
health: {"status":"ok","mock":false,"auth":{"ready":true,"require_auth":false}}
前端 / -> HTTP 200
前端: https://ai-native-d5gfb0dm2a28d1fe9-1419921079.tcloudbaseapp.com
后端: https://ai-native-d5gfb0dm2a28d1fe9-1419921079.ap-shanghai.app.tcloudbase.com
```
- 前端 `next build` 成功（15 页静态导出），静态托管上传 75 文件。
- 后端云函数更新完成，真实模式（BAILIAN_API_KEY 生效）在线。

## 四、测试与构建

- 后端：`pytest tests/` → **56 passed**（49 既有 + 4 条闭环）。
- 前端：`tsc --noEmit` → 0 error；`next build` 通过。

## 五、已知边界（诚实，非本次 P0 范围）

1. **mock 模式下的"取消"未生效**：`run_chat_agent` 在 `client.is_mock` 时短路到 `run_pipeline` 直线，取消标志未传入。真实模式（公网默认）取消已生效。修复需把取消标志传进 `run_pipeline` 或让 mock 也走工具循环，待排期。
2. **多 Agent 蜂群第 2–4 层仅规划/雏形**：黑板未落盘、平台 worker 未并行、无 waiting_user、未接多轮。第 1 层（完成真实性 / 交付闸门）已完整落地。蜂群默认关闭（`QIANAN_SWARM=1` 才开）。

## 六、演示视频录制建议（供本机录屏）

1. 打开公网 Demo，上传一张白底商品图 + 粘贴中文卖点（如"USB-C 快充便携榨汁杯，易清洗"）。
2. 勾选 5 个平台，点生成，展示右侧 SSE 面板：单平台逐个 `listing_update` 实时出现，最后 `done`。
3. 展开合规报告：47 项确定性校验，error 级问题自动回炉修订（留痕）。
4. 指代码证据：`server/tests/test_agent_loop.py` 的 4 条端到端测试，证明"提前提交被拒 / 超限不成功 / 未审核不可交付 / 全审核才完成"。

## 七、部署链路

- `cloudbase/deploy.sh`：CloudBase 云函数（Python3.10）+ 静态托管，一键同步 `app/` + `rules/` + linux cp310 依赖、物化密钥（用后即焚）、构建前端并部署。
- 密钥仅经临时物化配置注入云端环境变量，仓库不含明文（`.env` 已被 `.gitignore` 忽略）。
