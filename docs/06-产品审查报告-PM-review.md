# 千岸 QianAn 产品 / 演示完成度审查报告（PM 视角）

- **审查对象**：Simon Studio · AI+跨境黑客松巅峰赛·场景一「AI 智能上新」复赛作品
- **审查日期**：2026-09-03 ｜ **剩余开发期**：约 10 天（复赛 9.1–9.13）
- **审查方式**：实地读代码/文档 + 端到端实测交叉验证（非凭口头总结）

---

## 一句话总体判断
工程完整度已超多数黑客松作品、端到端链路真实跑通，是「能演示」的合格复赛作；但**缺失赛事最硬评分点「批量上架」**，且当前 Demo 在 `QIANAN_MOCK=1` 下主图为占位图、上架为本地模拟——补「真实感 + 三件提交物」才能冲奖。

## Strengths（已验证）
1. **规则引擎是真护城河**：`server/rules/` 5 平台 JSON + `compliance.py` 确定性校验（PIL 像素采样 / 正则 / 禁词 / 必填属性），非 LLM 幻觉，精准命中赛道「适配多平台规则」评分点（`compliance.py:222`）。
2. **端到端闭环真跑通**：`generate → heal → 5 平台 → files → publish → metrics → agent evolution`，21+ 接口真实存在（`main.py`）；一键上架用**真实 Playwright** 驱动 `/mock/seller-central` 并 5 步留痕截图（`runner.py` / `mock_browser.py`），比 PPT demo 可信度高。
3. **合规自愈是真 function-calling 回路**：`orchestrator._heal_listing` 模型决策 `revise/finish`，带 `heal_budget` 与 40s 墙钟预算，历史 `revised_total=3` 证明确实跑过（`orchestrator.py:123`）。
4. **Agent 进化 / 技能系统超出基础要求**：`memory_store` 蒸馏教训、`/api/agent/proposals` 进化提案、`/api/skills` 技能商店，叙事「越用越聪明」完整。

## Gaps / Risks（按严重度）

### 🔴 严重
- **G1 批量上架缺失**：赛事规则白纸黑字写「批量 Listing 与上架」，但后端无 batch 接口（`main.py` 仅单任务 `generate`）——最直接丢分点。
- **G2 Demo 主图是占位图**：`MOCK=1` 时 `visual.py:46` 返回 `mock://image/{platform}.jpg`，前端「主图」是假图，视觉生成卖点被证伪。
- **G3 提交物全 🚧**：Demo URL / 演示视频 / 源码仓库均未完成；`docs/05` 集成验证报告仍是模板占位（`⬜`、`<!-- -->`），无真实数据。

### 🟠 中等
- **R1 一键上架是本地模拟**：`/mock/seller-central` 是自写 FastAPI，`listing_id` 从 mock 页解析，非真实 Amazon。须明确标注 sandbox。
- **R2 metrics 为合成数据**：`/api/metrics` 来自 `/mock/api/metrics`，经营看板非真实回流。
- **R3 跨 session 脆弱**：uvicorn 不跨 turn 存活、`next dev` 需先清 `.next`、chromium 靠软链错位修复——现场演示易翻车。
- **R4 「38 项检查」数字**：视频脚本称 38 项，实际数由 rules JSON 的 `complianceChecks` 决定，需核对避免夸大。

### 🟡 轻
- `ideation` 选品较薄（3 市场 × 3 类目模板）；TikTok Shop 仅文案 + 视频脚本，未真生成视频（计划内简化，可接受）。

## Action List（按 ROI，剩 ~10 天）

| 优先级 | 动作 | 价值 | 风险 |
|---|---|---|---|
| **P0** | ① 切 `QIANAN_MOCK=0` 用真实主图 / A+ 录 3 分钟视频 | 修复 G2，假图→真图 | 中（耗 credit/网络） |
| **P0** | ② 补最小批量：前端多选商品 / 任务批量生成 + 进度汇总（复用 `generate`） | 补齐 G1 最大丢分项 | 低 |
| **P1** | ③ 固化一键启动脚本 + 部署拿 Demo URL | 消除 R3、交付 G3 | 低 |
| **P1** | ④ 上架页标「模拟卖家后台 sandbox」、metrics 标「演示数据」 | 降 R1/R2 误解 | 极低 |
| **P2** | ⑤ 填实 `docs/05` 验证报告 + 核对 38 项数字 | 交付物完整 | 低 |
| **P2** | ⑥ 备 2-3 个跨类目样例（3C / 家居 / 服饰） | 演示稳妥 | 低 |

## 如果只能做一件事
**做 ①（真实模式 + 录视频）**：当前最大可信度硬伤是「主图占位、整条链路在 mock 下跑」；一段用真实生成结果的 3 分钟视频能同时证明视觉能力、闭环与多平台差异。

**如果还能做第二件**：**做 ②（最小批量）**——它是赛事规则明文评分点，目前完全空缺。

## PM 核心判断
千岸的**工程深度已够**，离「拿奖」差的是三件交付物（真主图 demo / 批量能力 / 部署上线），而非技术——未来 10 天应从「写代码」转向「做可信演示 + 交齐材料」。
