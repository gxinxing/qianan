# 千岸 QianAn · PRD v1（铁腕审计版）

> ⚠️ **历史文档**：当前产品定义已迁移至 [`PRD-v2-从选品到上架闭环.md`](./PRD-v2-从选品到上架闭环.md)。本文档仅保留 2026-09-01 时的范围和决策记录，不再作为开发与验收依据。

> 审计日期：2026-09-01 · 复赛开发期 9.1–9.13
> 结论：核心链路（生成→体检→自愈→交付）已闭环，但**证据链可视化**与**交付最后一米**存在缺口，按 P0 清单收口。

## # Project DNA

一次输入商品信息，产出全平台（Amazon/Shopee/AliExpress/Lazada/TikTok Shop）**合规可上架**的完整商品包：多语言文案 + 规范主图 + A+ 详情 + 官方后台导入表——下载即用，不是聊天文本。

## # First Action Path

卖家粘贴商品名与卖点 → 一键生成 → 看 5 平台差异对比与合规报告 → 下载导入表/整包上架。

## # 用户与痛点锚定

目标用户：同时铺多平台的跨境卖家/品牌运营（SKU 多、上新频繁、无专职美工和翻译）。

| 卖家痛点 | 覆盖状态 |
|---|---|
| 一个 SKU 铺 5 平台，规则/语言/后台模板各不同 | ✅ 规则引擎 + 并行流水线 |
| 禁用词/字数/属性违规导致 listing 下架 | ✅ 确定性体检 + error 自动自愈重检 |
| 多语言本地化（泰/印尼/越/俄…）机翻生硬 | ✅ 按 rules.locales 输出（质量呈现待补 P1-6） |
| 主图规范（白底/尺寸/无字）美工成本高 | ⚠️ 图已生成，规范校验为骨架（P0-1） |
| 后台录入耗时易错 | ✅ Amazon Flat File / Shopee 批量上传 CSV |
| 选品不确定 | ✅ ideation 引流入口 |
| 批量上新 | ❌ 当前单 SKU（P1-5） |

## # Technical Constraints

- **Data Model**: `TaskRecord{task_id, status, stage, progress, request, understanding, listings[], created_at}`；`PlatformListing{platform, locales[], title, bullets[], description, attributes{}, images[], aplus[], compliance[], compliance_passed, revised_count}`；`Package{task.json, export.json, <platform>_import.csv, images/}`
- **State Machine**: `Task[queued → running(stage 五段) → done | failed]`，done 即落盘 packages，重启不丢
- **规则引擎非 LLM**：`rules/*.json`（rules.v1）是唯一事实源，代码直接消费，杜绝幻觉；`demoDepth` 诚实标注覆盖深度（deep/reuse/simple）
- **合规闭环**：确定性函数逐条执行 `complianceChecks`；error → `copy_agent.revise` 修订一次 → 复检 → `revised_count` 留痕
- **模型**：Token Plan 网关（qwen 文本 + 图像生成），全链路可降级 mock

## # Feature Spec（审计通过，仅此清单）

1. **商品理解**：输入 → 结构化提取（品类/卖点/关键词/属性）
2. **规则匹配**：读取 rules.v1 输出约束清单；新增透明页 `/rules` 展示（P0-3）
3. **多平台文案**：并行生成，按 locales 本地化，按平台长度/结构约束自适应
4. **主图生成**：按 `mainImage` 规范出图；PIL 校验尺寸/白底写入合规报告（P0-1）
5. **合规体检+自愈**：逐条校验 → error 回炉修订 → 复检 → 报告留痕
6. **交付包**：export.json + 各平台官方模板 CSV + 本地主图 + 整包 zip（P0-4）
7. **文件管理**：包列表/文件清单/下载/删除，后端重启不丢
8. **工作台**：上架前（输入）→ 上架中（进度轮询）→ 上架后（复盘+包）
9. **差异对比**：5 平台并排，字段差异琥珀高亮（路演核心视图）
10. **后台管理**：状态/平台/合规/自愈统计（功能冻结，不再加）
11. **选品灵感**：市场+类目 → 建议 → 一键填入（引流入口）
12. **利润测算**（9-01 新增）：确定性单位经济引擎——rules.economics 费率块（佣金/尾程 FBA 跳档/仓储/TACOS/退货率/VAT）+ `POST /api/economics` + 工作台上架前利润卡：输入采购价/重量/包装/市场带 → 每平台保本价、建议价、净利堆叠拆解、盈亏平衡销量、亏损红牌"建议放弃"

## # Not-To-Do List（复赛边界，防止自我膨胀）

- ❌ 平台 OpenAPI 直连上传（需卖家 OAuth 授权；演讲讲 roadmap：Shopee/TikTok Shop 均有开放 API）
- ❌ 多用户/登录/租户体系
- ❌ 上架后数据回流与选品归因分析
- ❌ videoScript 短视频产出（规则库字段保留但不实现）
- ❌ Qwen-VL 全量视觉校验（P0-1 只做确定性 PIL 尺寸+白底采样；VL 项在报告中标注"建议人工复核"）

## # P0 收口清单（9.2–9.4，演示决胜项）

1. **主图规范落地校验**：PIL 检查 宽高≥minWidth/minHeight + 四角像素白底采样；合规报告由"建议人工复核"升级为实测值（兑现规则库 image_spec 的 error 级承诺）
2. **结果页图片走本地文件服务**：当前直引 OSS 签名 URL（约 7 天过期），演示前旧任务图会裂；本地 packages 已有副本，结果页改为本地优先、OSS 兜底
3. **规则库透明页 `/rules`**：消费 `fetchRules`（现为死代码）+ bannedWords/长度规则/demoDepth 展示，直接回答评委"平台规则从哪来"
4. **整包 zip 下载**：`/api/files/{task_id}/zip`，一键拿走全部 CSV+主图+JSON

## # P1 差异化（9.5–9.8）

5. **批量模式**：工作台多 SKU 粘贴（一行一商品）→ 队列 → 批量进度（复用现有轮询框架）
6. **多语言质量呈现**：结果页按语言切换预览正文（让评委看到泰语/俄语真实内容，而非只有 locales 标签）

## # 竞争答问：为什么不用 GPT？

1. **确定性合规 vs 概率性输出**：GPT 会编造平台规则且每次对话需重新粘贴；QianAn 的规则库是结构化事实+代码执行，合规是"校验过的"，不是"模型自称合规的"
2. **交付即用 vs 聊天文本**：GPT 给一段文案，卖家自己查字数、翻译、填模板；QianAn 给完整上架包（CSV/A+/主图），下载即用
3. **一稿多岸 vs 单平台单次**：GPT 一次一个平台一个 SKU；QianAn 一次输入并行产出 5 平台差异化工件
4. **质量闭环**：体检→自愈→复检留痕，GPT 无回路

> 壁垒表述：**不是文笔**（模型同源），是"合规确定性 + 工程交付闭环"。路演不吹文案质量，吹交付确定性。
