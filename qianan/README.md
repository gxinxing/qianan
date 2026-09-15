# 千岸 QianAn — 一稿多岸的跨境上新 Agent

> 复赛 Demo 代码仓库 · 队伍 Simon Studio · 赛道：场景一 AI 智能上新
> 同一件商品，一个设计稿，铺到千片海岸。

上传一张商品图 + 中文卖点，约 90 秒并行生成 Amazon / Shopee / 速卖通 / Lazada / TikTok Shop
五个平台各自合规、可直接导入的上架包 + 合规报告。

---

## 架构

```
前端（Next.js + TS + Tailwind）
  上传页 / 结果页（5 平台 Tab + 差异对比 + 合规报告）
        │
后端（FastAPI）
  POST /api/generate → 异步任务；GET /api/tasks/{id} → 轮询进度与结果
        │
Agent 编排（主控 Orchestrator）
  ① 商品理解 Agent  → qwen3.7-max（结构化商品理解）
  ② 规则引擎（非 LLM）→ rules/*.json，确定性逻辑，护城河
  ③ 文案 Agent      → qwen3.7-max（多语言本地化，非直译）
  ④ 视觉 Agent      → qwen-image-2.0（平台规范主图）
  ⑤ 合规体检 Agent  → 规则驱动的真实校验（长度/禁词/必填属性…）
        │
阿里云百炼（黑客松 Token Plan 专属网关）
```

**关键设计**：规则引擎不是 LLM。`rules/` 目录是结构化事实，合规体检逐条执行
`complianceChecks`，不同平台必然产出不同结果（不是同一份文案换皮）。

## 目录结构

```
qianan/
├── rules/                # ★ 核心资产：5 平台规则库（rules.v1 schema）
├── server/               # FastAPI 后端 + Agent 编排
│   ├── app/
│   │   ├── main.py       # API 入口
│   │   ├── orchestrator.py
│   │   ├── agents/       # 五个 Agent
│   │   ├── bailian/      # 百炼网关客户端（真实 + Mock 双模式）
│   │   ├── .env          # 真实密钥（已 gitignore）
│   │   └── .env.example
│   └── requirements.txt
├── web/                  # Next.js 前端骨架（上传页 + 结果页）
└── scripts/
    └── smoke_test_bailian.py   # D1 冒烟测试（已实测通过）
```

## 快速开始

```bash
# 后端
cd server
cp .env.example .env          # 填入 BAILIAN_API_KEY（黑客松专属 key）
pip install -r requirements.txt
uvicorn app.main:app --reload --port 8000

# 前端
cd web
npm install
npm run dev                   # http://localhost:3000
```

无 key 或设 `QIANAN_MOCK=1` 时，后端自动进入 Mock 模式（全链路可联调，演示兜底）。

## Token Plan 专属网关（实测要点，2026-09-01）

专属 key（`sk-sp-` 开头）必须搭配专属基地址使用，协议细节与通用百炼不同：

| 能力 | 调用方式 |
|---|---|
| 文本生成 | `POST {base}/chat/completions`，OpenAI 格式；`enable_thinking: false` 关思考提速 |
| 图片生成 | **同样走 `/chat/completions`**，model 用图片模型，content 必须是列表格式 `[{"text": "..."}]`，图片 URL 在 `choices[0].message.content[0]["image"]`。`/images/generations` 路由不可用 |
| 视觉理解 | 网关暂无 VL 模型；商品理解走纯文本路径，配 `QIANAN_VL_MODEL` 后自动启用视觉路径 |

可用模型（以套餐清单为准）：文本 `qwen3.8-max / qwen3.7-max / qwen3.7-plus / qwen3.6-flash`…；
图片 `qwen-image-2.0(-pro) / wan2.7-image(-pro)`。

## 提交物清单（复赛 9.13 截止）

- [ ] 可访问 Demo 网址（前端 Vercel + 后端阿里云 FC / 轻量服务器）
- [ ] 3 分钟演示视频
- [ ] Demo 说明文档（架构图 + 操作指引 + 规则库说明）
- [ ] GitHub 代码仓库（注意：**.env 严禁提交**，公开仓库只放 .env.example）

## 下一步（对照复赛排期）

- D2 ✅ 规则库：5 平台 JSON 已建（Amazon / Shopee 做深）
- D1 ✅ 百炼环境：文本 + 图片生成实测跑通（scripts/smoke_test_bailian.py）
- D3–D5 ✅ 骨架：五 Agent 编排骨架 + 端到端真实链路已验证
- P0 ✅ 全部收口：主图 PIL 实测 / 图片本地化 / 规则透明页 / 整包 zip
- 设计 ✅ 全站视觉统一（2026-09-01）：Precision Tech 方向——Space Grotesk +
  IBM Plex Mono 双字体、brand/ink 色板（tailwind.config.js）、深海图 hero
  （contour-bg）、eyebrow/btn/card/field 组件类（globals.css）；8 个页面全部改造
- 待办：P1-6 多语言呈现（后端 _to_listing 丢弃了 per-locale 内容，需改数据模型 +
  前端语言切换）、P1-5 批量模式、git 仓库初始化 + GitHub 公开、部署（Vercel + FC）、
  3 分钟演示视频、Demo 说明文档
