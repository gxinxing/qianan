"""主控 Agent（Supervisor）：一个主 Agent 带着若干执行 Agent。

分工
----
- **主控（本文件）**：看黑板 → 从动作表里挑一个动作 → 派给对应的执行 agent → 观察结果 → 下一轮。
  它自己**不生成任何内容**，也不判断"能不能做"，只负责选择。
- **执行 agent**：`PlatformWorker`（文案 + 视觉）、`ReviewWorker`（独立审核，上下文隔离）。
  它们看不到彼此的推理，只通过黑板交换信息。

为什么这才是 agent 而不是 pipeline
--------------------------------
下一件事做什么是**模型在运行时看着黑板选的**，不是代码写死的顺序。
但「这一步是否允许执行」由 `ActionSpec.preconditions` 用代码判定 ——
模型提出一个当前不满足前置条件的动作时，执行器会**拒绝并告知原因**，
让模型换个动作。这就是「模型负责选择，代码负责判定」。

降级保证
--------
模型抽风 / 超轮数 / 网关异常时走 `deterministic_finish`，
用确定性路径把剩下的必备步骤补齐 —— **最差退化成一条流水线，不会比改造前更差**。
"""
from __future__ import annotations

import json
import logging
from typing import Any

from ...bailian.client import BailianLike, resolve_image_ref
from ...schemas import GenerateRequest, PlatformListing, TaskStatus
from ..compliance import ComplianceAgent
from ..copywriting import CopywritingAgent
from ..rules_engine import RulesEngineAgent
from ..understanding import ProductUnderstandingAgent
from ..visual import VisualAgent
from .blackboard import ActionSpec, Blackboard

logger = logging.getLogger(__name__)

SUPERVISOR_SYSTEM = """你是跨境上架任务的主控 Agent。你不生成内容，只做一件事：**看着黑板决定下一步做哪个动作**。

可用动作及含义：
1. understand_product —— 理解商品（通常第一步，必须先做）
2. generate_copy(platform) —— 为某平台生成文案
3. review_listing(platform) —— 审核某平台（独立执行，看不到写作者的推理）
4. revise_copy(platform) —— 按审核发现的问题修订文案（会使该平台审核结论作废，之后要重新 review）
5. generate_images(platform) —— 生成主图与详情图
6. generate_video(platform) —— 生成展示视频
7. submit_deliverable —— 交付。**只有全部平台都已生成、审核有效、且无阻断级问题时才能调用**

规则：
- 每次只选**一个**动作，做完看结果再决定下一个。
- 若某动作被拒绝（返回"无法执行"），说明它的前置条件没满足，换一个能做的。
- review 发现 error 就 revise_copy，改完**必须再 review 一次**才有效。
- 图片/视频是加分项但不是上架必需；时间和预算有限时可以不生成。
- 确认所有平台都合规后才 submit_deliverable。不要提前交付。"""


class Supervisor:
    """主控：持有黑板与动作表，驱动执行 agent 完成上架任务。"""

    def __init__(self, client: BailianLike, bb: Blackboard) -> None:
        self.client = client
        self.bb = bb
        self.listings: dict[str, PlatformListing] = {}
        self.understanding: Any = None
        self.image_ref: str | None = None

        # 执行 agent（延迟导入，避免 swarm 包内某个 worker 缺失时整个包不可用）
        from .platform_worker import PlatformWorker
        from .review_worker import ReviewWorker

        self.platform_worker = PlatformWorker(
            client, CopywritingAgent(client), VisualAgent(client), RulesEngineAgent()
        )
        self.review_worker = ReviewWorker(client, ComplianceAgent())
        self.understanding_agent = ProductUnderstandingAgent(client)

    # ---------------------------------------------------------- 动作表

    def action_table(self) -> list[ActionSpec]:
        """动作空间。前置条件是**代码判定**的依据，不是给模型看的装饰。"""
        platforms = list(self.bb.platforms)
        table: list[ActionSpec] = [
            ActionSpec(
                name="understand_product",
                description="理解商品，产出事实档案",
                preconditions=["always"],
                writes=["understanding"],
                cost="medium",
                idempotency_key="project+understanding_version",
            )
        ]
        for p in platforms:
            table += [
                ActionSpec(
                    name="generate_copy",
                    description=f"为 {p} 生成上架文案",
                    preconditions=["understanding.ready", f"rules.{p}.ready"],
                    writes=[f"copy.{p}"],
                    invalidates=[f"review.{p}"],
                    cost="medium",
                    idempotency_key=f"project+{p}+copy_version",
                ),
                ActionSpec(
                    name="review_listing",
                    description=f"独立审核 {p}（上下文隔离，不看写作者推理）",
                    preconditions=[f"copy.{p}.ready"],
                    writes=[f"review.{p}"],
                    cost="low",
                    isolated=True,
                    idempotency_key=f"project+{p}+copy_version",
                ),
                ActionSpec(
                    name="revise_copy",
                    description=f"修订 {p} 文案（会使审核失效，需重新审核）",
                    preconditions=[f"copy.{p}.ready"],
                    writes=[f"copy.{p}"],
                    invalidates=[f"review.{p}"],
                    cost="medium",
                    idempotency_key=f"project+{p}+copy_version",
                ),
                ActionSpec(
                    name="generate_images",
                    description=f"为 {p} 生成主图与详情图",
                    preconditions=[f"copy.{p}.ready"],
                    writes=[f"images.{p}"],
                    cost="high",
                    idempotency_key=f"project+{p}+images",
                ),
                ActionSpec(
                    name="generate_video",
                    description=f"为 {p} 生成展示视频",
                    preconditions=[f"images.{p}.ready"],
                    writes=[f"video.{p}"],
                    cost="high",
                    idempotency_key=f"project+{p}+video",
                ),
            ]
        table.append(
            ActionSpec(
                name="submit_deliverable",
                description="交付（需全部平台已生成、审核有效、无阻断问题）",
                preconditions=["all.copy.ready", "all.review.valid", "no.blocking"],
                writes=["delivery"],
                approval="none",
                cost="low",
            )
        )
        return table

    # ---------------------------------------------------------- 动作实现

    async def _act_understand(self, req: GenerateRequest) -> str:
        self.understanding = await self.understanding_agent.run(req, self.image_ref)
        self.bb.mark_understanding(self.understanding)
        self.bb.rules.update(RulesEngineAgent().run(list(self.bb.platforms)))
        return f"商品理解完成：{self.understanding.product_type or '—'}，已载入 {len(self.bb.rules)} 个平台规则。"

    async def _act_copy(self, req: GenerateRequest, platform: str) -> str:
        listing = await self.platform_worker.run_copy(self.bb, req, platform)
        if listing is None:
            return f"无法执行 generate_copy({platform})：文案生成失败，请换一个动作。"
        self.listings[platform] = listing
        return f"{listing.display_name or platform} 文案已生成（v{self.bb.platforms[platform].copy_version}）。"

    async def _act_review(self, platform: str, category: str) -> str:
        listing = self.listings.get(platform)
        if listing is None:
            return f"无法执行 review_listing({platform})：还没有产物。"
        issues = await self.review_worker.run(self.bb, listing, platform, category)
        blocking = [i for i in issues if i.severity == "error"]
        st = self.bb.platforms[platform]
        if blocking:
            fields = "、".join(dict.fromkeys(i.field for i in blocking))
            return f"{st.display_name or platform} 审核发现 {len(blocking)} 项阻断问题（{fields}），需要 revise_copy。"
        return f"{st.display_name or platform} 审核通过，审核结论有效。"

    async def _act_revise(self, platform: str) -> str:
        listing = self.listings.get(platform)
        st = self.bb.platforms[platform]
        if listing is None:
            return f"无法执行 revise_copy({platform})：还没有产物。"
        rules = self.bb.rules.get(platform) or {}
        errors = [i for i in listing.compliance if i.severity == "error" and i.field != "mainImage"]
        if not errors:
            return f"无法执行 revise_copy({platform})：当前没有需要修订的 error（缺图请用 generate_images）。"
        revised = await self.platform_worker.copy_agent.revise(listing, rules, errors)
        revised.revised_count += 1
        self.listings[platform] = revised
        self.bb.mark_copy(platform)  # 版本 +1 → 自动作废旧审核结论
        return (
            f"{st.display_name or platform} 已修订（第 {revised.revised_count} 轮），"
            f"审核结论已失效，请重新 review_listing。"
        )

    async def _act_images(self, platform: str) -> str:
        listing = self.listings.get(platform)
        if listing is None:
            return f"无法执行 generate_images({platform})：请先生成文案。"
        await self.platform_worker.run_visual(self.bb, listing, platform, self.image_ref)
        if not listing.images:
            return f"{platform} 图片生成未成功，但不阻断上架，可继续其他动作。"
        return f"{platform} 图片已生成（主图 {len(listing.images)} 张、详情图 {len(listing.detail_images or [])} 张）。"

    async def _act_video(self, platform: str) -> str:
        listing = self.listings.get(platform)
        if listing is None:
            return f"无法执行 generate_video({platform})：请先生成文案。"
        try:
            await self.platform_worker.visual_agent.run_video(self.understanding, listing)
        except Exception as exc:  # noqa: BLE001 —— 视频是加分项，失败不阻断
            logger.warning("视频生成失败: %s", exc)
            return f"{platform} 视频生成失败（{exc}），不影响上架，可跳过。"
        self.bb.mark_video(platform)
        return f"{platform} 展示视频已生成。"

    async def _act_deliver(self) -> str:
        self.bb.status = "completed"
        return f"交付完成：{len(self.listings)}/{len(self.bb.platforms)} 个平台，全部通过审核。"

    # ---------------------------------------------------------- 主循环

    async def run(self, req: GenerateRequest, task=None, should_stop=None) -> dict:
        """驱动整个上架任务。返回 {"status", "listings", "blackboard", "actions"}。

        should_stop：取消信号。必须一路传到工具循环，否则「停止」在蜂群模式下又失效。
        """
        from ...agent_core.loop import run_tool_loop
        from ...agent_core.registry import ToolSpec

        self.image_ref = resolve_image_ref(req.image_url, req.image_base64)
        self.req = req  # handler 通过 self 取，避免闭包传参出错
        self.bb.rules.update(RulesEngineAgent().run(list(self.bb.platforms)))

        # ---- 把动作表转成工具；每个 handler 执行前先由代码校验前置条件 ----
        table = self.action_table()

        async def _guarded(spec: ActionSpec, coro_factory) -> str:
            """代码判定：前置条件不满足就拒绝执行，把原因告诉模型让它换动作。"""
            blocked = spec.blocked_by(self.bb)
            if blocked:
                self.bb.log_action(spec.name, "guard", False, f"前置条件不满足: {blocked}")
                return (
                    f"无法执行 {spec.name}：前置条件不满足 —— {'、'.join(blocked)}。"
                    f"请换一个当前能做的动作。"
                )
            out = await coro_factory()
            self.bb.log_action(spec.name, "worker", True, str(out)[:120])
            return out

        async def h_understand() -> str:
            return await _guarded(table[0], lambda: self._act_understand(req))

        tools: list[ToolSpec] = [
            ToolSpec(
                name="understand_product",
                description="理解商品，产出事实档案。通常是第一步。",
                parameters={"type": "object", "properties": {}, "required": []},
                handler=h_understand,
            )
        ]

        # 为每个平台注册带平台参数的动作（跳过全局动作）
        for spec in table:
            if spec.name in ("understand_product", "submit_deliverable"):
                continue
            for p in self.bb.platforms:
                tools.append(self._platform_tool(spec, p, _guarded))

        async def h_deliver() -> str:
            deliver_spec = next(s for s in table if s.name == "submit_deliverable")
            return await _guarded(deliver_spec, self._act_deliver)

        tools.append(
            ToolSpec(
                name="submit_deliverable",
                description="交付。仅在全部平台已生成、审核有效且无阻断问题时可用。",
                parameters={"type": "object", "properties": {}, "required": []},
                handler=h_deliver,
            )
        )

        user_prompt = (
            f"商品名称：{req.product_name or '(从图片识别)'}\n"
            f"卖点：{req.selling_points or '(从图片识别)'}\n"
            f"类目：{req.category}\n"
            f"目标平台：{', '.join(self.bb.platforms)}\n"
            f"{'有商品图片' if self.image_ref else '没有商品图片'}\n\n"
            f"当前黑板状态：{json.dumps(self.bb.observe(), ensure_ascii=False)}\n\n"
            f"请一步步选择动作，直到可以 submit_deliverable。"
        )

        result = await run_tool_loop(
            self.client,
            SUPERVISOR_SYSTEM,
            user_prompt,
            tools,
            max_rounds=30,
            deadline_s=self.bb.budget["max_seconds"],
            should_stop=should_stop,
        )

        if result.get("cancelled"):
            self.bb.status = "cancelled"
            self.bb.log_action("cancel", "guard", True, result.get("reason", "用户取消"))
            return {
                "status": self.bb.status,
                "listings": list(self.listings.values()),
                "blackboard": self.bb.snapshot(),
                "actions": self.bb.action_history,
                "fallback": False,
                "reason": result.get("reason", ""),
                "cancelled": True,
            }

        # ---- 降级：模型没走完就用确定性路径补齐，最差也是一条流水线 ----
        if self.bb.status != "completed":
            await self.deterministic_finish(req)

        return {
            "status": self.bb.status,
            "listings": list(self.listings.values()),
            "blackboard": self.bb.snapshot(),
            "actions": self.bb.action_history,
            "fallback": result.get("fallback", False),
            "reason": result.get("reason", ""),
            "cancelled": result.get("cancelled", False),
        }

    def _platform_tool(self, spec: ActionSpec, platform: str, _guarded):
        """把一个带平台参数的 ActionSpec 转成 ToolSpec（含前置条件守卫）。"""
        from ...agent_core.registry import ToolSpec

        async def handler() -> str:
            action = {
                "generate_copy": lambda: self._act_copy(self.req, platform),
                "review_listing": lambda: self._act_review(platform, self.req.category),
                "revise_copy": lambda: self._act_revise(platform),
                "generate_images": lambda: self._act_images(platform),
                "generate_video": lambda: self._act_video(platform),
            }.get(spec.name)
            if action is None:
                return f"动作 {spec.name} 未实现。"
            return await _guarded(spec, action)

        return ToolSpec(
            name=f"{spec.name}__{platform}",
            description=f"{spec.description}（前置条件：{'、'.join(spec.preconditions)}）",
            parameters={"type": "object", "properties": {}, "required": []},
            handler=handler,
        )

    # ---------------------------------------------------------- 确定性兜底

    async def deterministic_finish(self, req: GenerateRequest) -> None:
        """模型没走完时，用确定性路径补齐必备步骤。

        只补「上架必需」的：理解 → 文案 → 审核 → 修订重审。
        图片/视频不补（加分项，且耗时）。
        保证最差退化成流水线，不会比改造前更差。
        """
        try:
            if self.understanding is None:
                await self._act_understand(req)
            for p in self.bb.platforms:
                st = self.bb.platforms[p]
                for _ in range(2):  # 最多修订一轮
                    if not st.has_copy:
                        await self._act_copy(req, p)
                    if not st.review_valid:
                        await self._act_review(p, req.category)
                    st = self.bb.platforms[p]
                    if st.review_valid and not st.blocking_issues:
                        break
                    if st.blocking_issues:
                        await self._act_revise(p)
        except Exception as exc:  # noqa: BLE001 —— 兜底路径失败也不能让任务崩
            logger.warning("确定性兜底失败: %s", exc)
            self.bb.last_error = f"{type(exc).__name__}: {exc}"

        unfinished = [
            p for p, s in self.bb.platforms.items()
            if not (s.review_valid and not s.blocking_issues)
        ]
        if unfinished:
            self.bb.status = "partial"
            self.bb.open_issues.append(f"未完成平台：{', '.join(unfinished)}")
        elif self.bb.status != "completed":
            self.bb.status = "completed"

    @staticmethod
    def to_task_status(bb_status: str) -> TaskStatus:
        return {
            "completed": TaskStatus.done,
            "partial": TaskStatus.partial,
            "cancelled": TaskStatus.cancelled,
            "failed": TaskStatus.failed,
        }.get(bb_status, TaskStatus.partial)
