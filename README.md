# 千岸 QianAn — 一稿多岸的跨境上新 Agent

> 同一件商品，摆上全球每一个货架。一个设计稿，铺到千片海岸。

## 项目简介

把卖家上传的一张商品图 + 一段中文卖点，自动生成 **Amazon / Shopee / 速卖通 / Lazada / TikTok Shop** 5 个平台各自合规的上架包（多语言文案 + 规范主图 + A+ 详情 + 后台导入 CSV + 合规报告）。

从 3–7 天人工制作，压到约 90 秒 AI 一键生成（单平台约 30 秒，5 平台并行约 90 秒；**该耗时与并发为已有测试样本下的实测值，非对所有商品/网络的普遍保证**）。

## 技术栈

| 层 | 选型 |
|---|---|
| Backend | FastAPI + Python 3.10 + Pydantic v2 |
| AI 模型 | 文本/视觉理解：阿里云百炼 Qwen（Qwen-Max 多语言 + Qwen-VL 视觉理解）；商品图生成：经 **TokenDance 网关**调用 Seedream-5.0-lite（并非直接走百炼 Wanx） |
| Frontend | Next.js 15 + TypeScript + Tailwind CSS |
| Agent 编排 | 自研轻量框架（tool loop + function calling） |
| 部署 | 阿里云函数计算 FC / 轻量应用服务器 + Vercel（前端） |

## 差异化亮点

1. **多平台规则引擎**：不是简单生成文案，而是按各平台结构化规则（标题字符限制、禁用词、类目属性、图片规范等）做"规则翻译"，5 个平台的输出各有不同。
2. **合规预检 + 自愈循环**：47 项确定性校验，error 级问题自动回炉修订，复检留痕。
3. **设计师级视觉规范**：以图改图优先，保持商品本体不变，仅按平台规范调整背景与构图。

## 目录结构

```
qianan/
├── server/
│   ├── app/
│   │   ├── agents/          # 5 个 Agent（理解/规则/文案/视觉/合规）
│   │   ├── agent_core/      # Agent 运行时（tool loop / registry / trace）
│   │   ├── bailian/         # 阿里云百炼客户端封装
│   │   ├── publisher/       # 上架执行器（Playwright mock 后台）
│   │   ├── main.py          # FastAPI 入口（21 个 API 接口）
│   │   ├── orchestrator.py  # 6 阶段流水线编排
│   │   ├── schemas.py       # Pydantic 数据模型
│   │   ├── task_store.py    # 内存任务存储
│   │   ├── file_store.py    # 生成结果文件仓库
│   │   └── ...
│   ├── rules/               # 5 平台规则 JSON（由根 qianan/rules 同步，make sync-rules）
│   ├── data/
│   │   ├── tasks/           # 任务产物（运行时生成）
│   │   └── skills/          # 已安装技能（规则补丁 + 工具扩展）
│   ├── requirements.txt
│   ├── .env.example
│   └── Dockerfile
├── web/
│   ├── app/                 # Next.js App Router 页面
│   ├── components/          # 公共组件
│   ├── lib/                 # API 调用层 + 工具函数
│   └── package.json
├── docs/
│   ├── 00-赛事规则.md
│   ├── 01-选题分析.md
│   ├── 02-创意方案.md
│   ├── 03-复赛Demo开发计划.md
│   └── 04-演示视频脚本.md
└── qianan-dsh/              # DeepSeek Harness 集成（Skills + Profile）
```

## 快速启动

### 环境要求

- Python 3.10+
- Node.js 18+
- 阿里云百炼平台 API Key（比赛 Token Plan 发放）

### 后端

```bash
cd qianan/server
pip install -r requirements.txt
cp .env.example .env          # 填入 BAILIAN_API_KEY
uvicorn app.main:app --reload --port 8000
```

### 前端

```bash
cd qianan/web
npm install
npm run dev                   # http://localhost:3000
```

### 验证

```bash
# 后端健康检查
curl http://localhost:8000/api/health

# 查看 API 文档（Swagger UI）
open http://localhost:8000/docs
```

## API 接口总览

| 接口 | 方法 | 说明 |
|---|---|---|
| `/api/health` | GET | 健康检查 |
| `/api/generate` | POST | 创建上架任务（上传图 + 卖点） |
| `/api/tasks/{id}` | GET | 查询任务详情（含进度与产物） |
| `/api/tasks/{id}/export` | GET | 导出完整上架包 |
| `/api/rules` | GET | 平台规则库总览 |
| `/api/audit` | POST | 合规体检（单平台字段校验） |
| `/api/ideation` | POST | AI 选品灵感 |
| `/api/economics` | POST | 单位经济测算（5 平台盈亏分析） |
| `/api/publish` | POST | 确认上架（审批闸口 + Playwright 执行留痕） |
| `/api/files` | GET | 文件仓库列表 |
| `/api/feedback` | POST | 人类反馈（打分/评价） |
| `/api/skills` | GET/POST/DELETE | 技能商店（规则补丁 + 工具扩展） |

完整接口详情见后端 `main.py` 或 Swagger 文档。

## 项目架构

```
用户输入（白底图 + 中文卖点）
        │
        ▼
  ┌─────────────┐
  │ 主控 Orchestrator │
  └──────┬──────┘
         ├── ① 商品理解 Agent    → Qwen-VL
         ├── ② 规则引擎（结构化 JSON）
         ├── ③ 文案 Agent        → Qwen-Max（多语言）
         ├── ④ 视觉 Agent        → Wanx（文生图/以图改图）
         └── ⑤ 合规体检 Agent    → 规则校验 + PIL 实测
              │
              ▼
       ⑥ 反思 Agent（蒸馏教训入记忆库）
              │
              ▼
    5 平台上架包 + 合规报告 + 导入 CSV
```

## Docker 部署

```bash
# 本地一键启动
docker-compose up --build

# 后端：http://localhost:8000
# 前端：http://localhost:3000
```

## 决赛交付状态（2026-09-15 收口）

| 项目 | 状态 | 链接 / 位置 |
|---|---|---|
| 公网 Demo（前端） | ✅ 已部署，HTTP 200 | https://ai-native-d5gfb0dm2a28d1fe9-1419921079.tcloudbaseapp.com |
| 公网 API（真实模式） | ✅ 在线（mock:false） | https://ai-native-d5gfb0dm2a28d1fe9-1419921079.ap-shanghai.app.tcloudbase.com/api |
| 源代码仓库 | ✅ 已推送 `main` | https://github.com/gxinxing/qianan （HEAD `main`） |
| 技术说明 | ✅ | `FINAL-DELIVERY.md`（决赛总览）+ `docs/`；复赛作品 `submission/SimonStudio_千岸QianAn_复赛作品.docx` 为复赛版 |
| Agent 闭环验收测试 | ✅ 56 passed（含 4 条端到端） | `qianan/server/tests/test_agent_loop.py` |
| 演示视频 | 🚧 待本机录屏 | 访问上方公网 Demo 即可录制（建议脚本见 `FINAL-DELIVERY.md`） |

> 部署链路：`cloudbase/deploy.sh`（CloudBase 云函数 + 静态托管，9/7 全链路实测，今日含 P0 修复重部署）。
> 限流与游客归属：`/api/chat` 接 `require_user` + `uid_of`（游客按 IP+UA 派生独立 uid）+ `check_rate_limit`，公开地址不会被反复调用烧完额度。
> 数据留存（诚实）：任务产物 `task.json` / `export.json` 及生成上架包**持久化于服务端**供续查与导出，并非"处理完即弃"；演示数据按游客 uid 隔离。

## 许可证

MIT
