# 千岸 QianAn · DSH Profile（能力插件包）

> 把千岸的上新能力拆成 **7 个宿主无关的能力包**：每个都是「一份 SKILL.md + 一个 Python 实现 + 自带数据」，可以装进 DSH，也可以装进别的 agent 宿主。

## 这是什么 / 不是什么

**是**：千岸核心能力（规则引擎、单位经济、合规体检、文案、视觉、选品、商品理解）的**可插拔封装**。
**不是**：千岸主产品。线上产品跑在 `../qianan/server`（FastAPI），本目录是它的能力出口，不参与线上链路。

这么切分是刻意的：**能力做成自包含单元 = 资产（能装进任何宿主）；绑死某个宿主 = 风险。**

## 自检（4 条，全部应通过）

```bash
export QIANAN_RULES_DIR="$PWD/data/rules"

npm run test:skills      # → All 7 skills OK
npm run test:rules       # → Loaded 5 platforms: [...]
npm run test:economics   # → Economics test OK: 5 platforms
npm run test:compliance  # → Compliance test OK: passed=True, issues=0
```

> 需要 `Pillow`（`compliance_check` 用它实测图片尺寸）。

## 7 个能力包：自包含度

| 能力包 | 依赖 | 能否零配置跑 | 说明 |
|---|---|---|---|
| `rules_engine` | 无 | **✅ 是** | 自带 5 平台规则 JSON；纯确定性，不用 LLM —— 千岸的护城河 |
| `economics` | 无 | **✅ 是** | 纯数学引擎：5 平台保本价 / 建议价 / 净利 / 盈亏判定 |
| `compliance_check` | Pillow | **✅ 是** | 纯规则校验 + PIL 实测主图尺寸 |
| `visual_agent` | 提示词文件 | 部分 | 提示词构建可跑；真出图需图片网关 |
| `product_understanding` | 提示词文件 | 部分 | 提示词加载可跑；真识别需 LLM |
| `copywriting` | 提示词文件 | 部分 | 提示词加载可跑；真生成需 LLM |
| `ideation` | 提示词文件 | 部分 | 提示词加载可跑；真生成需 LLM |

前 3 个**不碰网络、不需要 key**，是演示"能力可插拔"最干净的样本。

## 安装到 DSH

DSH 的 profile 是「一串 plugin-bundle patch 层 + 你自己的覆盖层」，任何 npm 包都能作为一层加进来：

```bash
dsh plugin --profile <你的 profile> add <本包>
```

`package.json` 的 `dsh.profile.bundles` 已经声明了所需的 12 个 bundle（DSH 官方 + 第三方），`dsh.agents.pipeline` 声明了 7 个能力的执行顺序。

## 已知未完成（诚实清单）

| 项 | 状态 | 影响 |
|---|---|---|
| `cordis.patch.yml` | **空数组 `[]`** | 注释里写的"扩展 dsh-genui 做沉浸式电商 demo"**未实现** |
| `agents/*/`（7 个入口目录） | **只有空 `__init__.py`** | `cordis.yml` 的 `entry:` 指向空目录，未接线 |
| `agents.defaults.mock` | **`true`** | 7 个能力默认走 mock，接真网关需另配 |
| 依赖 | **未安装** | 装依赖需切官方 npm 源（淘宝镜像版本滞后） |
| `cordis.yml` 的 `pipeline` | **写死顺序** | 无条件分支、无并行，与主仓 `orchestrator.py` 是同一形态 |

## 目录

```
skills/           7 个能力包（每个含 SKILL.md + skill_impl.py）
skills/prompts/   6 份系统提示词（由 skills.prompts.load 加载）
skills/schemas.py 本包独立的数据模型
agents/           7 个 agent 入口目录（待接线）
data/rules/       5 平台规则 JSON（rules_engine 的数据源）
cordis.yml        agent 注册表 + pipeline 声明
```
