"""独立审核 Worker：对单个平台产物做两层审核，并把结论写回黑板。

**上下文隔离（本项目的硬性约束）**：本 worker 只读两样东西——
`bb.understanding`（商品事实，唯一事实来源）与产物本身 `PlatformListing`，
绝不接触写作者生成文案时的任何中间推理或 prompt。
一旦让审核者看到"写作者本来想表达什么"，它就会被带着走，从而放过事实性错误；
所以隔离不是洁癖，而是审核结论可用的前提。

两层审核的分工：
1. 规则引擎（`ComplianceAgent.run`）—— 确定性、不调模型，是合规护城河，必须跑；
2. 语义审核（`review_listing`）—— 调模型，查事实一致性，属于增强项。

因此语义层失败只降级（记日志后丢弃），绝不牵连规则层结果：
**阻断与否永远由规则引擎说了算。**
"""
from __future__ import annotations

import logging

from ...bailian.client import BailianLike
from ...schemas import ComplianceIssue, PlatformListing, Understanding
from ..compliance import ComplianceAgent
from ..review import review_listing
from .blackboard import Blackboard

logger = logging.getLogger(__name__)


class ReviewWorker:
    """单平台产物的独立审核器。

    只报告问题，不改文案——改文案是 writer / reviser 的职责，
    审核与修改由不同 agent 承担，才能避免"自己给自己批改作业"。
    """

    def __init__(self, client: BailianLike, compliance_agent: ComplianceAgent | None = None) -> None:
        self.client = client
        self.compliance_agent = compliance_agent or ComplianceAgent()

    async def run(
        self,
        bb: Blackboard,
        listing: PlatformListing,
        platform: str,
        category: str,
    ) -> list[ComplianceIssue]:
        """审核单个平台产物，返回全部问题（error + warn）。

        流程：规则引擎 →（可选）语义审核 → 合并写回 listing.compliance → mark_reviewed。
        `mark_reviewed` 会把 review_version 对齐到当前 copy_version，
        表示"此刻的审核结论有效"；之后文案再改，结论自动作废。
        """
        rules = bb.rules.get(platform, {})

        # 第一层：规则引擎（确定性，不调模型）。结果原地写入 listing.compliance。
        self.compliance_agent.run(listing, rules, category)
        issues: list[ComplianceIssue] = list(listing.compliance)

        # 第二层：语义审核（事实一致性）。仅在真实模型 + 事实档案就绪时才有意义。
        understanding: Understanding | None = bb.understanding
        if not self.client.is_mock and understanding is not None:
            try:
                semantic = await review_listing(self.client, listing, understanding)
            except Exception as exc:  # noqa: BLE001 —— 语义层是增强项，失败不得拖垮整轮审核
                logger.warning("语义审核失败，降级为仅规则引擎结果（%s）: %s", platform, exc)
            else:
                if semantic:
                    issues.extend(semantic)

        # 回写产物：把语义问题并入 listing.compliance，保持列表与审核结论一致。
        listing.compliance = issues
        listing.compliance_passed = not any(i.severity == "error" for i in issues)

        # 回写黑板：blocking_issues 按 i.get("severity") 取值，故必须转成 dict。
        bb.mark_reviewed(platform, [i.model_dump() for i in issues])

        errors = sum(1 for i in issues if i.severity == "error")
        logger.info(
            "审核完成 platform=%s 规则+语义共 %d 条（error=%d, warn=%d）",
            platform,
            len(issues),
            errors,
            len(issues) - errors,
        )
        return issues
