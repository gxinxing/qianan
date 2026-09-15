# 千岸 QianAn — 决赛交付清单（2026-09-15 收口）

> 一稿多岸的跨境上新 Agent：1 张商品图 + 一段中文卖点 → 自动生成 Amazon / Shopee / 速卖通 / Lazada / TikTok Shop 5 平台合规上架包。单平台约 30 秒、5 平台并行约 90 秒（均为单商品测试样本下的实测值，非普遍保证）。

## 一、交付物总览

| 交付物 | 状态 | 位置 / 链接 |
|---|---|---|
| 源代码仓库 | ✅ 已推送 `main` | https://github.com/gxinxing/qianan （HEAD `main`） |
| 公网 Demo（前端） | ✅ 已部署，HTTP 200 | https://ai-native-d5gfb0dm2a28d1fe9-1419921079.tcloudbaseapp.com |
| 公网 API | ✅ 真实模式在线（mock:false） | https://ai-native-d5gfb0dm2a28d1fe9-1419921079.ap-shanghai.app.tcloudbase.com/api |
| 技术说明文档 | ✅ | `submission/SimonStudio_千岸QianAn_复赛作品.docx` + `docs/`（01–14） |
| Agent 闭环验收测试 | ✅ 56 passed（含 4 条端到端） | `qianan/server/tests/test_agent_loop.py` |
| 最终提交整合包 | ✅ 已生成 | `submission/final-submission.zip`（含复赛 Word + 源码 ZIP + 本清单 + README）|
| 演示视频 | 🚧 待本机录屏 | 访问上方公网 Demo 录制即可（脚本见第六节）|

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

### 端到端完整流程证据（可复现，本次实测）

- **完整链路跑通 + 闸门生效（审计 #3 实证）**：本地 `run_pipeline` 用 mock 客户端（不依赖外网图床，排除网络抖动）实测——
  - 单平台 Amazon → `status=done`，产物齐全（标题✓ / 5 条五点✓ / 主图✓ / 合规通过✓）；
  - 双平台 Amazon+Shopee → Shopee 因产出 **0 条五点描述**被交付闸门拦下 → 整体 `partial`（**绝不标 done**）。
  - 这直接证明「缺必需产物就不宣称完成」的修复已落地，不是纸面声明。
- **真实模型路径在线**：本地 `get_client()` 返回 `is_mock=False`（BAILIAN_API_KEY 生效）；公网 `/api/health` 返回 `mock:false`，真实模式在线。
- **后端测试 56 passed**：含 4 条端到端驱动 `run_chat_agent` 主循环（提前提交被拒 / 循环超限不成功 / 未审核不可交付 / 全审核才完成）+ 闸门 + 批量，覆盖审计全部确定性故障。
- **公网 SCF 同步生成超时（已知限制，非本次 P0）**：`/api/generate` 在 `TENCENT_SCF=1` 下走同步分支（SCF 无后台进程，异步 task 会被冻结），叠加云函数 120s 超时，真实模式多平台/复杂商品可能超时。规避：演示走 `/api/chat`（SSE 流式，连接保持不超时）或单平台简单商品；或本地 `python -m uvicorn app.main:app --port 8001` 起服务（异步分支，立即返回 task_id + 前端轮询）。

## 三、公网冒烟证据（2026-09-15 部署后）

```
health: {"status":"ok","mock":false,"auth":{"ready":true,"require_auth":false}}
前端 / -> HTTP 200
前端: https://ai-native-d5gfb0dm2a28d1fe9-1419921079.tcloudbaseapp.com
后端: https://ai-native-d5gfb0dm2a28d1fe9-1419921079.ap-shanghai.app.tcloudbase.com
```
- 前端 `next build` 成功（15 页静态导出），静态托管上传 75 文件。
- 后端云函数更新完成，真实模式（BAILIAN_API_KEY 生效）在线。

### 浏览器连通性验证（2026-09-15，真实 Chromium）

> 说明：此前"HTTP 200 即连通"的判断过宽（`curl` 不执行 CORS 检查）。以下为**浏览器层面**的实测，口径收窄为"浏览器跨域读取已通过"。

用真实 Chromium（无头）打开已部署前端域，在页面上下文（源 = `https://…tcloudbaseapp.com`）向 API（`https://…ap-shanghai.app.tcloudbase.com`）发起**跨域** fetch，由浏览器强制 CORS：

```
GET  /api/health          -> 200，响应体可读：{"status":"ok","mock":false,...}
                             网络层 access-control-allow-origin: https://…tcloudbaseapp.com（单个）
GET  /api/tasks/__probe__ -> 404，响应体可读：{"detail":"task not found"}
                             网络层 access-control-allow-origin: https://…tcloudbaseapp.com（单个）
```

- 浏览器**成功读取响应体** ⇒ CORS 放行（若被拒，浏览器抛 `TypeError: Failed to fetch` 且读不到 body）。
- 网络层原始头为**单个** `access-control-allow-origin`，无逗号拼接重复 ⇒ 无"重复头被浏览器拒绝"的问题。
- （注：`response.headers.get('access-control-allow-origin')` 在页面脚本里返回 `null` 属**正常**——浏览器按设计不向脚本暴露 CORS 响应头，判断是否放行应以"能否读到 body"为准。）
- 结论：**后端 API 与前端域之间的浏览器通信正常**；阻碍在**前端测试域名**本身（见第五节第 5 条）。

#### 前端页面真实流程验证（2026-09-15，真实 Chromium 驱动实际页面）

> 补充：上面只是"页面上下文里的 fetch"；这一次是**真的打开 /workbench 页面、填表、点生成按钮**，走完整 UI 流程。

本地起 `next dev`（:3001）指向**已部署云端真实后端**（CORS 网关回显 Origin，游客模式 `require_auth:false`），用无头 Chromium 驱动：

```
1) 打开 http://localhost:3001/workbench  → 未跳转 /login（游客放行，/api/health 探测成功）
2) 填商品名「便携榨汁杯 380ml」+ 中文卖点 → 勾选平台 → 点「生成 N 平台上架包」
3) 页面发出真实 POST /api/generate，请求体字段与后端契约一致：
   {"product_name":"便携榨汁杯 380ml",
    "selling_points":"USB-C 快充，10 秒出汁，杯身可拆洗…",   ← 字符串，非数组
    "category":"home_kitchen",
    "platforms":["shopee","aliexpress","lazada","tiktokshop"]}  ← tiktokshop 键正确
4) 结果：cors_errors=[]，visible_error=null，其它 API(/api/health,/api/files,/api/admin/*) 全部 200
```

- **结论：前端页面与后端连通、表单提交链路打通、字段契约正确**，不存在"CORS 拦页面"或"点了没反应"的问题。
- 诚实边界：本次观察窗口内**未等到 `/api/generate` 的响应体**——云端为 SCF 同步模式，长任务会挂到约 120s 才返回（已知限制第 3 条），属时序问题非连通失败；请求已确证发出并被后端接收。
- 阻碍仍未变：公网**前端测试域名**显示「访问量已达上限」，浏览器进不去应用（见第五节第 5 条），故真实页面验证是在**本地 dev + 云端后端**组合下完成的。

## 四、测试与构建

- 后端：`pytest tests/` → **56 passed**（49 既有 + 4 条闭环）。
- 前端：`tsc --noEmit` → 0 error；`next build` 通过。

## 五、已知边界（诚实，非本次 P0 范围）

1. **mock 模式下的"取消"未生效**：`run_chat_agent` 在 `client.is_mock` 时短路到 `run_pipeline` 直线，取消标志未传入。真实模式（公网默认）取消已生效。修复需把取消标志传进 `run_pipeline` 或让 mock 也走工具循环，待排期。
2. **多 Agent 蜂群第 2–4 层仅规划/雏形**：黑板未落盘、平台 worker 未并行、无 waiting_user、未接多轮。第 1 层（完成真实性 / 交付闸门）已完整落地。蜂群默认关闭（`QIANAN_SWARM=1` 才开）。
3. **公网 `/api/generate` 同步生成有 120s 云函数超时**：真实模式多平台/复杂商品可能超时（证据段已说明，演示走 `/api/chat` 或单平台规避）。如需公网大批量生成，建议提高 SCF 函数超时或改异步调用模式，待排期。
4. **CORS：当前无重复头，已加固防复发**。CORS 头共有两层可能来源：① CloudBase 网关——对 `/api/**` 所有响应注入，实测回显请求里的 `Origin`（连 `http://localhost:3000` 也回显，即 reflect 模式）；② 后端 FastAPI `CORSMiddleware`——**仅当 `QIANAN_ENABLE_CORS=1` 时才启用**（`server/app/main.py:89`）。云端 `cloudbaserc.json` 未设该变量（默认关）→ 当前只有网关注入，实测所有端点（`/api/health` 200、`/api/tasks/{id}` 404、`OPTIONS` 预检 204）返回的 `access-control-allow-origin` 均为**单个、正确值**。历史上你看到的 `origin,origin` 重复头，唯一成因是**两层同时注入**（后端 `=1` + 网关同时写），与 `main.py:86-88` 的注释警告一致；现已在 `cloudbaserc.json` 显式写死 `"QIANAN_ENABLE_CORS": "0"`，每次部署归一为关，杜绝复发。
5. **CloudBase 测试域名挡路（非 P0，但直接影响评审访问）**。前端测试域名 `*.tcloudbaseapp.com` 首次访问会先弹「页面访问提示（风险提醒）」页（需 4 秒倒计时后点「确定访问」）；且当前该页已显示「**当前访问量已达上限，如需继续访问，请联系开发者**」——测试域名访问配额已耗尽，**浏览器里进不去应用**。这是演示/评审的真实阻塞点，与 CORS 无关（后端 API 域不受影响）。解决：绑定已备案自有域名到静态托管（风险提示与配额限制同时消失），或按提示页链接「我是开发者，如何去掉当前页面？」在控制台处理；录屏演示亦可临时用本地 dev server。

## 六、演示视频录制建议（供本机录屏）

> ⚠️ 录制前先解决第五节第 5 条：公网测试域名当前被「访问量已达上限」挡住。稳妥做法是**用本地 dev server 录屏**（`server: python -m uvicorn app.main:app --port 8001`；`web: npm run dev`，`NEXT_PUBLIC_API_BASE=http://localhost:8001`），或先绑定自有域名。

1. 打开 Demo（本地或自有域名），上传一张白底商品图 + 粘贴中文卖点（如"USB-C 快充便携榨汁杯，易清洗"）。
2. 勾选 5 个平台，点生成，展示右侧 SSE 面板：单平台逐个 `listing_update` 实时出现，最后 `done`。
3. 展开合规报告：47 项确定性校验，error 级问题自动回炉修订（留痕）。
4. 指代码证据：`server/tests/test_agent_loop.py` 的 4 条端到端测试，证明"提前提交被拒 / 超限不成功 / 未审核不可交付 / 全审核才完成"。

## 七、部署链路

- `cloudbase/deploy.sh`：CloudBase 云函数（Python3.10）+ 静态托管，一键同步 `app/` + `rules/` + linux cp310 依赖、物化密钥（用后即焚）、构建前端并部署。
- 密钥仅经临时物化配置注入云端环境变量，仓库不含明文（`.env` 已被 `.gitignore` 忽略）。
