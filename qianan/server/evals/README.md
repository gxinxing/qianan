# 千岸 Evals — 快照式合规评测集

## 怎么跑

```bash
cd server && /usr/bin/python3 -m evals.run
```

跑完打印摘要（总/passed/failed/skipped、failed 用例与引擎缺口 note），并把完整 JSON 报告写入 `server/data/evals/report.json`。

## 用例来源

- **规则快照用例**（`cases.py` 前 8 个 suite）：直接构造 `PlatformListing` 中间状态 + 加载平台规则（`app.rules_store.load_rules`，即 `rules/*.json`），调用 `ComplianceAgent.run(listing, rules, category)`，断言产出的 issue 集合（field + severity + 关键 message 片段）。覆盖长度、五点逐条长度、条数、禁用词、必填属性、必备段落（lazada 真实启用）、主图规格（本地 data URI 构图 + PIL 实测，无外网依赖）、语言覆盖，以及 amazon/shopee/aliexpress/lazada 的平台差异化规则（标题上限 128/120/200/255、禁用词 severity 差异）。
- **历史事故用例**（`incidents_history` suite）：把 `server/data/memory/experiences.jsonl` 的 8 条教训（材质未知宣称不锈钢、silicone 冒称 food grade、未验证 Leak Proof、编造耐温数值、未授权品牌词、绝对化极限词、编造双层真空、编造电池性能）编码成负面前置条件用例。引擎能抓到 → passed；抓不到 → failed，note 写明「规则引擎缺口：XXX」——这是评测集的核心产出，不允许为了通过而改产品代码。

## 报告去向与前端关系

`report.json` 遵循固定 schema（`generated_at / total / passed / failed / skipped / duration_ms / suites[].cases[]`，got/expect 均为简短人类可读中文），供 B 模块前端 `/agent` 页的「评测」面板消费：passed 即合规引擎当前能力快照，failed 的 note 即引擎缺口清单（每条对应一条可落地的规则补丁/新检查项需求）。

注意：规则加载沿用生产路径 `app/rules_store.py`（实际指向仓库根 `rules/` 目录）；单用例异常不会炸 runner，会计入 failed 并附 note。
