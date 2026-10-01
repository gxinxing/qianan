# 千岸 QianAn 项目交接文档

更新时间：2026-10-01  
用途：让新加入的伙伴在不依赖口头补充的情况下，理解项目目标、当前实现、运行方式、已知问题和协作入口。

## 1. 项目是什么

千岸（QianAn）面向跨境电商卖家。用户提供商品图片和中文卖点，系统协助生成 Amazon、Shopee、速卖通、Lazada、TikTok Shop 的平台化商品上架内容、图片与合规检查结果。产品核心不是把同一份文案翻译五遍，而是结合平台规则生成和校验不同结构的上架内容。

目标用户：需要把商品快速铺到多个跨境平台的中小卖家/运营人员。项目目前是黑客松后形成的可演示原型，不能把历史测试样本的“约 90 秒”或合规结果理解成对任意商品和网络环境的 SLA 或保证。

## 2. 当前仓库状态

- GitHub：<https://github.com/gxinxing/qianan>。截至本交接更新时间，仓库可见性已通过 GitHub API 确认为 **Private**；协作者需要仓库所有者邀请并授予访问权限。
- 主分支：`main`。本机交接时 HEAD 为 `aa95989`（`docs: archive submission deliverables, roadshow deck, and decision records`），已推送到 `origin/main`。
- 仓库有多个历史阶段留下的说明文档。README 与早期复赛方案存在过时配置/计划；实际动手前请以代码、`.env.example`、`FINAL-DELIVERY.md` 和本文件交叉确认，遇到冲突以当前实现为准。
- 主要应用位于 `qianan/`：FastAPI 后端、Next.js 前端和平台规则库。
- `qianan-dsh/` 是 DeepSeek Harness / DSH 技能集成资料，不是主 Web 应用的启动入口。
- `cloudbase/` 保存 CloudBase 部署脚本和配置；`docs/`、`submission/` 保存赛事背景、审查记录和交付材料。

## 3. 代码结构与请求链路

```text
qianan/web/                 Next.js 15 + React 19 前端
  app/                      页面与路由
  components/               UI 组件
  hooks/useChat.ts           SSE 聊天/产物事件消费
  lib/                       API 与通用逻辑

qianan/server/              FastAPI 后端
  app/main.py                HTTP API 入口
  app/orchestrator.py        生成流水线编排
  app/agents/                商品理解、规则、文案、视觉、合规等 Agent
  app/agent_core/            工具循环、工具注册和运行轨迹
  app/bailian/               模型网关客户端
  app/mcp_server.py          MCP stdio 服务入口
  rules/                     后端运行时规则副本
  tests/                     后端回归测试
  data/                      运行时任务与产物数据

qianan/rules/               五个平台规则源；同步到 server/rules 的机制见 Makefile
qianan/extension/           浏览器扩展
qianan-dsh/                 DSH profile 与技能示例
cloudbase/                  CloudBase 部署相关
docs/                       设计、赛事、审查、架构演进记录
submission/                 比赛提交文件和路演材料
```

主流程是：前端提交商品信息 → `main.py` 创建任务或建立聊天 SSE → Agent/编排逻辑按平台规则生成内容 → 视觉生成与合规校验 → 交付闸门检查必需产物和审核状态 → 前端展示各平台结果、进度及报告。对话流事件包括 `listing_update`、`listing_full` 和 `done`；前端处理逻辑在 `qianan/web/hooks/useChat.ts`。不能只看 HTTP 200 判断任务成功，业务完成状态应以任务状态和交付闸门结果为准。

架构和收口细节见 [`FINAL-DELIVERY.md`](FINAL-DELIVERY.md)、[`docs/14-多Agent蜂群架构.md`](docs/14-多Agent蜂群架构.md) 与 [`docs/15-决赛路演讲稿与Agent架构演进说明.md`](docs/15-决赛路演讲稿与Agent架构演进说明.md)。

## 4. 技术栈与外部依赖

- 前端：Next.js 15、React 19、TypeScript、Tailwind CSS。
- 后端：Python 3.10、FastAPI、Pydantic v2、Uvicorn。
- 文本/视觉模型由后端网关配置决定；图片生成也由对应网关和模型配置决定。不要依赖旧 README 中的某个模型名作为固定事实。
- 服务端数据当前包括任务和生成产物。部署/清理前先明确这些文件是否需要保留。
- 历史部署说明记录了 CloudBase 前端静态托管与云函数 API。部署状态、配额、域名可用性和云端密钥都是时变信息，需要在控制台重新核实；`FINAL-DELIVERY.md` 的线上状态是 2026-09-15 的快照，不代表今天仍在线。

## 5. 本地运行

### 后端

```bash
cd qianan/server
python3.10 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
# 编辑 .env：本地联调可设 QIANAN_MOCK=1；真实模型需配置有权限的网关 Key 和对应 Base URL。
uvicorn app.main:app --reload --port 8000
```

健康检查：`http://localhost:8000/api/health`；API 文档：`http://localhost:8000/docs`。

### 前端

另开终端：

```bash
cd qianan/web
npm install
npm run dev
```

前端默认开发地址为 `http://localhost:3000`。若要连非默认 API，请查看 `qianan/web` 中 API base URL 的配置读取方式，并按 Next.js 的构建期环境变量规则设置。

### Docker Compose

根目录提供 `docker-compose.yml`，前后端默认分别映射到 `localhost:3000` 和 `localhost:8100`。Compose 配置引用 `qianan/server/.env`，运行前需准备该文件；无真实 Key 时将 `QIANAN_MOCK=1`。启动：

```bash
docker compose up --build
```

## 6. 配置与凭据

`qianan/server/.env.example` 是变量模板。常用项包括：

- `BAILIAN_API_KEY`、`BAILIAN_BASE_URL`：文本模型网关凭据与地址。
- `QIANAN_TEXT_MODEL`、`QIANAN_IMAGE_MODEL`、`QIANAN_VL_MODEL`：模型选择。
- `QIANAN_MOCK`：`1` 使用 Mock，`0` 尝试真实服务。
- `QIANAN_REQUIRE_AUTH`、`QIANAN_JWT_SECRET`：鉴权开关及签名密钥。

不要把 `.env`、云端密钥、个人 Token、真实用户数据或可复用的截图凭据提交到 Git。每位伙伴在本地独立配置凭据；需要共享云资源时，通过安全的密钥管理渠道授权，不要把秘密写进交接文档或聊天记录。公开演示环境的 Key、限额和游客访问能力也应由负责人单独管理。

## 7. 已完成的能力和可靠性边界

已落地的核心包括：多平台规则 JSON、商品理解/文案/视觉/合规等 Agent、生成与聊天接口、SSE 产物面板、规则检查、导出能力、部分经济测算/选品/发布与技能接口、MCP 服务入口，以及交付完成闸门。能力入口和实际可用范围请以当前 API、代码和测试为准。

`FINAL-DELIVERY.md` 记录了 2026-09-15 收口时后端 82 项测试通过和前端构建/类型检查通过。它还指出以下待跟进边界：

1. Mock 聊天路径的取消行为未完整贯穿流水线。
2. 蜂群架构后续层仍属规划/雏形；蜂群默认关闭，需显式设置 `QIANAN_SWARM=1` 才启用相关路径。
3. CloudBase 云函数下同步 `/api/generate` 可能接近 120 秒限制；需重新评估部署平台、超时配置或异步方案。
4. 旧 CloudBase 测试域名曾遇访问配额限制；当前线上访问情况需实际复查。

这些是历史记录中的边界，接手后应先复现、确认是否仍存在，再更新状态，不要直接当作现时已验证事实。

## 8. 推荐的共同推进顺序

先由伙伴一起确认目标用户、演示/商业化目标和当前部署现状，再按下面顺序推进：

1. **建立共同基线**：双方取得私有仓库访问权；确认 `main` 最新提交、运行环境、模型网关权限、线上环境归属；本地 Mock 模式启动并完成一次端到端操作。
2. **验证核心体验**：选择一件代表性商品，完整跑通图片/卖点输入、平台结果、合规问题解释、导出。记录失败环节和响应时间，不用单次顺利结果外推普遍性能。
3. **复核当前风险**：运行后端测试及前端 typecheck/build，复测取消、超时、SSE 中断/恢复、空产物交付闸门、游客隔离和限流；核验现有云端是否仍可访问。
4. **决定最近一个里程碑**：建议优先完成真实用户试用的闭环与可靠性修复，再决定多 Agent 蜂群、批量处理或接入更多平台。每个里程碑写清负责人、验收条件和完成证据。
5. **持续维护文档**：改动 API、部署方式、模型供应商、密钥变量或架构边界时，同步更新 README/本交接文档和相关 `docs/`，并注明日期。

### 合作分工建议

- 产品/业务伙伴：访谈卖家、梳理真实平台工作流和规则需求、定义优先用户与验收样例。
- 工程伙伴：本地复现、端到端链路、API/Agent/前端实现、回归和部署自动化。
- 双方共同负责：规则来源核验、真实样例验收、模型成本/延迟记录、发布前检查和优先级决策。

开始时请明确一位变更负责人维护主分支；功能开发用短分支和小 PR，PR 描述包含问题、改动、验证结果和遗留事项。涉及平台规则时附来源链接与核验日期，避免把模型生成的规则当成平台官方政策。

## 9. 建议优先处理的交接事项

- 邀请共同开发伙伴进入私有 GitHub 仓库，并确认其能克隆、推送分支和创建 PR。
- 确认 `.env.example` 中当前支持的模型配置是否与团队可用账号一致；用 Mock 作为无凭据联调基线。
- 复核线上 Demo / API、CloudBase 账号持有人、部署权限、域名配额和密钥轮换方式。
- 从 `FINAL-DELIVERY.md` 的边界列表中选一个首要改进项，建立 issue 并写验收条件。
- 检查 `README.md`、`qianan/README.md` 和该文档之间是否还存在重要矛盾，逐步把 README 更新成对新伙伴友好的快速入口。

## 10. 建议阅读顺序

1. 本文，了解项目上下文和当前协作基线。
2. [`README.md`](README.md)，查看仓库介绍和基础启动指引（部分内容可能来自较早阶段）。
3. [`FINAL-DELIVERY.md`](FINAL-DELIVERY.md)，了解决赛收口记录、测试证据和已知边界。
4. [`docs/14-多Agent蜂群架构.md`](docs/14-多Agent蜂群架构.md) 与 [`docs/12-Agent-Harness架构评估与改造路径.md`](docs/12-Agent-Harness架构评估与改造路径.md)，理解 Agent 运行时与演进计划。
5. `qianan/server/app/main.py`、`qianan/server/app/orchestrator.py`、`qianan/web/hooks/useChat.ts`，沿主链路读代码。
6. `qianan/rules/` 与相关测试，理解平台规则和交付验收口径。

