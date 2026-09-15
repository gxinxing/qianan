"""千岸数据模型（pydantic v2）。"""
from __future__ import annotations

import time
from enum import Enum
from typing import Any, Optional

from pydantic import BaseModel, Field

ALL_PLATFORMS = ["amazon", "shopee", "aliexpress", "lazada", "tiktokshop"]

# ---------- 规划动作空间（Step 1：让「规划」真正改变执行图） ----------
#
# 规划器只能对 OPTIONAL_ACTIONS 行使裁量权；FORCED_ACTIONS 是合规与交付底线，
# 由 policy 层拦截，规划器提交了也会被忽略（见 orchestrator.plan_task）。

#: 可选动作：耗时/成本高，且是否产出不影响「合规上架包」的成立。
OPTIONAL_ACTIONS = ("generate_detail_shots", "generate_video")

#: 强制动作：跳过会导致交付物不完整或合规失守，不接受规划器跳过。
FORCED_ACTIONS = (
    "understand_product",
    "match_rules",
    "generate_copy",
    "generate_visual",
    "audit_compliance",
    "reflect_memory",
)

ALL_ACTIONS = FORCED_ACTIONS + OPTIONAL_ACTIONS

#: 动作 → 中文名（留痕可读 + 与前端展示对齐）
ACTION_LABELS = {
    "understand_product": "商品理解",
    "match_rules": "规则匹配",
    "generate_copy": "多语言文案",
    "generate_visual": "规范主图",
    "generate_detail_shots": "多角度详情图",
    "generate_video": "展示视频",
    "audit_compliance": "合规体检",
    "reflect_memory": "反思回写记忆",
}

# ---------- 输入理解第二层：意图（用户到底要什么） ----------
#
# 第一层商品理解（Understanding）回答「这是什么商品」；
# 本层回答「用户要干什么」，并由此划定本次任务的**动作空间** ——
# 意图先圈出允许的动作集合，规划器再在这个集合内选路。

GOAL_FULL_PACKAGE = "full_package"
GOAL_PREVIEW = "preview"

ALL_GOALS = (GOAL_FULL_PACKAGE, GOAL_PREVIEW)

GOAL_LABELS = {
    GOAL_FULL_PACKAGE: "出完整上架包",
    GOAL_PREVIEW: "先出方案，暂不生成",
}

#: 意图 → 本次允许进入执行图的动作集合
GOAL_ACTIONS: dict[str, tuple[str, ...]] = {
    # 完整包：全量动作（具体选项由规划器在 OPTIONAL_ACTIONS 内决定）
    GOAL_FULL_PACKAGE: ALL_ACTIONS,
    # 方案预览：只做「读懂商品 + 匹配规则」，产出上新策略报告，不生成任何上架物料。
    # 不产出上架包 ⇒ 没有可上架的产物 ⇒ 无需合规体检（guardrail 保护的是产物本身）。
    GOAL_PREVIEW: ("understand_product", "match_rules"),
}


def actions_for_goal(goal: str) -> set[str]:
    """本次意图允许的动作集合（未知意图一律按完整包处理，不做静默降级）。"""
    return set(GOAL_ACTIONS.get(goal, GOAL_ACTIONS[GOAL_FULL_PACKAGE]))


class Intent(BaseModel):
    """输入理解的第二层：用户到底要什么。

    由意图 Agent 从诉求文本判定；`platforms` 支持从自然语言里抽取
    （如「只铺 Amazon 和 Shopee」），非空时覆盖请求里的平台选择。
    """

    goal: str = GOAL_FULL_PACKAGE
    platforms: list[str] = Field(default_factory=list, description="从诉求中解析出的目标平台（空 = 沿用请求）")
    summary: str = Field(default="", description="一句话复述用户诉求，供用户核对，避免误判")
    confidence: float = 1.0
    decided_by: str = "planner"  # planner = 模型判定 / default = 未写诉求 / fallback = 判定失败兜底
    excluded_actions: list[str] = Field(
        default_factory=list,
        description="本次意图不包含的动作（相对完整动作空间）—— 意图改变执行图的直接证据",
    )


class IdeationRequest(BaseModel):
    """选品灵感输入：目标市场 + 类目方向。"""

    market: str = Field(default="global", description="目标市场: us / sea / global")
    category: str = Field(default="home_kitchen", description="类目方向: electronics / home_kitchen / apparel")


class IdeationSuggestion(BaseModel):
    """单条选品建议，可一键填入主表单。"""

    product_name: str
    reason: str = ""
    selling_points: str = ""
    category: str = "home_kitchen"


class AblationConfig(BaseModel):
    """消融实验配置：控制各 Agentic 组件的启用/禁用（默认全开 = 完整管线）。

    用于 ablation study：逐个关闭组件，度量对输出质量的影响。
    所有字段默认 False = 组件正常运行；True = 跳过该组件。
    """

    disable_plan: bool = Field(default=False, description="跳过规划阶段，直接用默认计划")
    disable_memory: bool = Field(default=False, description="跳过长期记忆召回与注入")
    disable_heal: bool = Field(default=False, description="跳过合规自愈循环")
    disable_reflect: bool = Field(default=False, description="跳过反思阶段（不回写记忆）")
    force_skip: list[str] = Field(
        default_factory=list,
        description=(
            "验证通道：绕过规划器强制跳过指定可选动作（仅 OPTIONAL_ACTIONS 内有效）。"
            "用于证明「执行图确实随规划改变」——若强制跳过耗时没有下降，说明执行器没真消费规划。"
        ),
    )


class GenerateRequest(BaseModel):
    """一稿输入：一张白底主图 + 中文卖点。"""

    product_name: str = Field(default="", max_length=200, description="商品名称（≤200 字符，可空=完全看图识别）")
    selling_points: str = Field(default="", max_length=2000, description="卖点描述（≤2000 字符，可空=纯看图识别）")
    request_text: str = Field(
        default="",
        max_length=300,
        description="用户的一句话诉求（可空 = 默认出完整上架包），如「先别生成，我想看看你打算怎么做」",
    )
    category: str = Field(default="home_kitchen", description="类目: electronics / home_kitchen / apparel")
    image_url: Optional[str] = Field(default=None, description="商品图公网 URL（仅 https）")
    image_base64: Optional[str] = Field(default=None, max_length=20_000_000, description="商品图 base64（≤20MB）")
    platforms: list[str] = Field(default_factory=lambda: list(ALL_PLATFORMS), max_length=10)
    ablation: Optional[AblationConfig] = Field(default=None, description="消融实验配置（默认 None = 完整管线）")


class BatchGenerateRequest(BaseModel):
    """批量上新：一次提交多个商品，逐一对齐各平台生成合规 Listing 并上架。

    用于赛事场景一「批量完成 Listing 撰写与后台上架」评分点。
    """

    items: list[GenerateRequest] = Field(
        default_factory=list,
        max_length=20,
        description="商品清单（≤20 个）；每个元素即一次单品生成的输入",
    )
    platforms: Optional[list[str]] = Field(
        default=None,
        description="可选：统一覆盖所有商品的平台清单；不传则各自沿用 items[].platforms",
    )


class AuditRequest(BaseModel):
    """表单草稿体检：字段来自卖家后台表单（浏览器侧边栏场景），复用流水线合规引擎。"""

    platform: str = Field(default="amazon")
    category: str = Field(default="home_kitchen")
    title: str = ""
    bullets: list[str] = Field(default_factory=list)
    description: str = ""
    attributes: dict[str, str] = Field(default_factory=dict)
    images: list[str] = Field(default_factory=list)


class TaskStatus(str, Enum):
    queued = "queued"
    running = "running"
    done = "done"
    failed = "failed"
    # partial：跑出了一部分产物但**未收敛**（超轮数 / 超墙钟 / 网关异常 / 用户取消）。
    # 与 done 的区别是决定性的：done 表示通过了交付闸门，partial 表示没有。
    partial = "partial"
    cancelled = "cancelled"


class Understanding(BaseModel):
    """商品理解 Agent 的结构化输出。"""

    category: str = ""
    product_type: str = ""
    material: str = ""
    attributes: dict[str, str] = Field(default_factory=dict)
    selling_points: list[str] = Field(default_factory=list)
    target_audience: str = ""
    keywords: list[str] = Field(default_factory=list)


class ComplianceIssue(BaseModel):
    check_id: str
    severity: str  # error / warn
    field: str
    message: str


class TraceEvent(BaseModel):
    """Agent 工具调用轨迹：规划/工具循环/反思的每一步留痕，供结果页与 /agent 页回放。"""

    ts: float = Field(default_factory=time.time)
    phase: str = ""  # plan / build / heal / reflect / evolve
    tool: str = ""
    args_summary: str = ""
    result_summary: str = ""
    status: str = "ok"  # ok / error / fallback


class TaskPlan(BaseModel):
    """⓪ 规划 Agent 的决策产物。

    持久化而非只留痕，是为了让"自主规划"可被回放：策略由模型在调研工具
    （竞品价格带 / 准入合规 / 平台热搜）之后自主决定，而非硬编码流水线。

    注意 `strategy` 只是给人看的文本；**真正改变执行图的是 `skip`**——
    规划器据此从执行图中移除可选动作，`skipped_actions` 记录实际生效的跳过项，
    两者对照即可验证"规划是否真的被消费"，而不是只留了一条好看的日志。
    """

    strategy: str = ""
    heal_budget: int = 1
    focus: str = ""
    research_tools: list[str] = Field(default_factory=list, description="规划前自主调研所调用的工具名")
    decided_by: str = "planner"  # planner = 模型决策 / fallback = 回退默认计划
    #: 规划器声明的跳过项（仅 OPTIONAL_ACTIONS 内有效，其余会被 policy 忽略）
    skip: list[str] = Field(default_factory=list, description="规划器自主跳过的可选动作名")
    #: 执行层实际生效的跳过项 —— 规划被消费的直接证据
    skipped_actions: list[str] = Field(default_factory=list, description="执行器实际跳过的动作名")


class MemoryLesson(BaseModel):
    """被召回并注入文案提示词的一条历史教训（长期记忆的证据单元）。"""

    lesson: str = ""
    platform: str = ""
    hit_count: int = 0  # 该教训历史被注入次数 —— 跨任务复用强度的直接证据
    source_task: str = ""


class AgentReflection(BaseModel):
    """⑥ 反思 Agent 蒸馏出的新教训，将写入长期记忆供后续任务复用。"""

    platform: str = ""
    lesson: str = ""


class Feedback(BaseModel):
    """人对单平台上架包的显式反馈：喂给记忆库与进化 Agent（SFT 数据积累）。"""

    task_id: str
    platform: str
    rating: int = Field(..., description="1 = 好评 / -1 = 差评")
    comment: str = ""


class AplusModule(BaseModel):
    """A+ 详情页模块：headline 横幅 / grid 卖点阵 / compare 规格表 / story 品牌故事。"""

    type: str = "headline"
    title: str = ""
    text: str = ""
    items: list[dict[str, str]] = Field(default_factory=list)


class PlatformListing(BaseModel):
    """单平台上架包。"""

    platform: str
    display_name: str = ""
    locales: list[str] = Field(default_factory=list)
    title: str = ""
    bullets: list[str] = Field(default_factory=list)
    description: str = ""
    attributes: dict[str, str] = Field(default_factory=dict)
    images: list[str] = Field(default_factory=list)
    detail_images: list[str] = Field(default_factory=list, description="详情图（面料特写/上身场景/平铺搭配等）")
    video_url: Optional[str] = Field(default=None, description="展示视频 URL（图生视频）")
    aplus: list[AplusModule] = Field(default_factory=list)
    video_script: Optional[dict[str, Any]] = None
    compliance: list[ComplianceIssue] = Field(default_factory=list)
    compliance_passed: bool = True
    revised_count: int = 0


class TaskRecord(BaseModel):
    task_id: str
    status: TaskStatus = TaskStatus.queued
    stage: str = ""
    progress: float = 0.0
    request: GenerateRequest
    understanding: Optional[Understanding] = None
    listings: list[PlatformListing] = Field(default_factory=list)
    trace: list[TraceEvent] = Field(default_factory=list)
    # —— 四项 Agentic 能力的结构化证据（供前端回放，不止于日志流）——
    intent: Optional[Intent] = None                              # 输入理解②：意图判定
    plan: Optional[TaskPlan] = None                              # 自主规划
    memory_recall: list[MemoryLesson] = Field(default_factory=list)  # 长期记忆
    reflections: list[AgentReflection] = Field(default_factory=list)  # 反思迭代
    strategy_report: Optional[str] = Field(default=None, description="上新策略报告（用户可读交付物）")
    error: Optional[str] = None
    created_at: float = Field(default_factory=time.time)
    #: 归属租户：CloudBase access_token 换出的 uid（匿名 = "anonymous"）
    owner_uid: str = ""


# ---------- 上架执行（PRD v0.3） ----------

class PublishStatus(str, Enum):
    queued = "queued"
    running = "running"
    live = "live"
    failed = "failed"


class PublishStep(BaseModel):
    """执行器单步留痕：动作 + 细节 + 截图（可观测性硬约束，无留痕视同黑盒）。"""

    ts: float = Field(default_factory=time.time)
    action: str = ""  # open_page / fill_fields / upload_image / submit / live_confirm
    detail: str = ""
    screenshot: Optional[str] = None


class PublishJob(BaseModel):
    """一次上架执行：queued → running → live | failed；failed 可重试（≤2 次指数退避）。"""

    job_id: str
    task_id: str
    platform: str
    executor: str = "mock_browser"  # mock_browser / extension_assist / computer_use（占位）
    status: PublishStatus = PublishStatus.queued
    attempts: int = 0
    last_error: Optional[str] = None
    live_url: Optional[str] = None
    listing_id: Optional[str] = None
    sku: str = ""
    published_at: Optional[float] = None
    created_at: float = Field(default_factory=time.time)
    steps: list[PublishStep] = Field(default_factory=list)


class PublishRequest(BaseModel):
    """确认上架请求：approved 必须由用户在结果页显式置真（硬闸口，严禁无人值守上架）。"""

    task_id: str
    platform: str
    approved: bool = False
