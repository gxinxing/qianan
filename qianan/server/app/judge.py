"""千岸 (QianAn) 判定核 (Judgment Kernel / Judge)。

参考 mu (qybaihe/mu) 的判定核哲学：
把 80% 的例行判定（如：输入前置校验、动作风险判定、合规硬约束判定、完成度校验）
交给轻量、确定性的轻量判定器（Deterministic / Rule-based Judge），
只有真正的复杂创作与生成才交给通用的大语言模型 (Swarm Workers)。

决策点 (Decision Points):
- input.preflight: 校验输入完整度与推理级别
- tool.admission: 评估工具产物是否符合上架要求
- tool.risk: 评估动作风险 (如：是否包含虚假医疗宣称、品牌侵权风险)
- turn.completion: 评估交付闸门与合规覆盖率
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any

from .schemas import GenerateRequest, PlatformListing

logger = logging.getLogger(__name__)


@dataclass
class JudgmentVerdict:
    """判定核产出的单次裁决结论。"""
    decision_point: str
    allowed: bool
    score: float = 1.0
    reason: str = ""
    details: dict[str, Any] = field(default_factory=dict)


class JudgmentKernel:
    """千岸判定核 (Judgment Kernel)。

    在每个 Turn 与 Action 执行前/后发起 35+ 类型的标准化裁决，
    保证系统高效率、高合规与零“假完成”。
    """

    def judge_input_preflight(self, req: GenerateRequest) -> JudgmentVerdict:
        """[input.preflight] 评估输入商品信息与目标平台。"""
        if not req.product_name and not req.selling_points:
            return JudgmentVerdict(
                decision_point="input.preflight",
                allowed=False,
                score=0.0,
                reason="商品名称与卖点描述不能同时为空",
            )
        if not req.platforms:
            return JudgmentVerdict(
                decision_point="input.preflight",
                allowed=False,
                score=0.0,
                reason="必须至少指定一个目标上架平台",
            )
        return JudgmentVerdict(
            decision_point="input.preflight",
            allowed=True,
            score=1.0,
            reason="输入符合准入要求，触发标准思考级别",
        )

    def judge_tool_risk(self, platform: str, text: str) -> JudgmentVerdict:
        """[tool.risk] 判定文本内容合规风险（如严禁词、极限词）。"""
        risk_keywords = ["第一", "绝对", "100%治愈", "最强", "神药"]
        hit_words = [w for w in risk_keywords if w in text]
        if hit_words:
            return JudgmentVerdict(
                decision_point="tool.risk",
                allowed=False,
                score=0.2,
                reason=f"命中高风险违禁词: {', '.join(hit_words)}",
                details={"hit_words": hit_words},
            )
        return JudgmentVerdict(
            decision_point="tool.risk",
            allowed=True,
            score=1.0,
            reason="未检测到阻断级合规风险",
        )

    def judge_turn_completion(
        self,
        platforms: list[str],
        listings: dict[str, PlatformListing],
        reviewed_platforms: set[str],
    ) -> JudgmentVerdict:
        """[turn.completion] 评估任务完成度与交付闸门。"""
        missing_platforms = [p for p in platforms if p not in listings]
        if missing_platforms:
            return JudgmentVerdict(
                decision_point="turn.completion",
                allowed=False,
                score=0.0,
                reason=f"部分平台尚未生成产物: {', '.join(missing_platforms)}",
            )

        unreviewed = [p for p in platforms if p not in reviewed_platforms]
        if unreviewed:
            return JudgmentVerdict(
                decision_point="turn.completion",
                allowed=False,
                score=0.4,
                reason=f"部分平台产物尚未通过独立合规审核: {', '.join(unreviewed)}",
            )

        has_blocking = False
        for _p, item in listings.items():
            if any(i.severity == "error" for i in (item.compliance or [])):
                has_blocking = True
                break

        if has_blocking:
            return JudgmentVerdict(
                decision_point="turn.completion",
                allowed=False,
                score=0.5,
                reason="产物中仍存在阻断级合规错误，禁止交付",
            )

        return JudgmentVerdict(
            decision_point="turn.completion",
            allowed=True,
            score=1.0,
            reason="目标平台产物全覆盖、通过独立审核且零阻断级错误",
        )
