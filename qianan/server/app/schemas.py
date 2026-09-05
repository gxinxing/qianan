"""千岸数据模型（pydantic v2）。"""
from __future__ import annotations

import time
from enum import Enum
from typing import Any, Optional

from pydantic import BaseModel, Field

ALL_PLATFORMS = ["amazon", "shopee", "aliexpress", "lazada", "tiktokshop"]


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


class GenerateRequest(BaseModel):
    """一稿输入：一张白底主图 + 中文卖点。"""

    product_name: str = Field(default="", max_length=200, description="商品名称（≤200 字符，可空=完全看图识别）")
    selling_points: str = Field(default="", max_length=2000, description="卖点描述（≤2000 字符，可空=纯看图识别）")
    category: str = Field(default="home_kitchen", description="类目: electronics / home_kitchen / apparel")
    image_url: Optional[str] = Field(default=None, description="商品图公网 URL（仅 https）")
    image_base64: Optional[str] = Field(default=None, max_length=20_000_000, description="商品图 base64（≤20MB）")
    platforms: list[str] = Field(default_factory=lambda: list(ALL_PLATFORMS), max_length=10)


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
    """

    strategy: str = ""
    heal_budget: int = 1
    focus: str = ""
    research_tools: list[str] = Field(default_factory=list, description="规划前自主调研所调用的工具名")
    decided_by: str = "planner"  # planner = 模型决策 / fallback = 回退默认计划


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
    plan: Optional[TaskPlan] = None                              # 自主规划
    memory_recall: list[MemoryLesson] = Field(default_factory=list)  # 长期记忆
    reflections: list[AgentReflection] = Field(default_factory=list)  # 反思迭代
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
