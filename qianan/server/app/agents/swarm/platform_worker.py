"""平台执行 worker：对单个平台跑完「文案生成 + 视觉素材」的闭环，并把结果写回黑板。

它只做执行，不做决策——「这一步该不该做」由主控依据 ActionSpec 的前置条件判定，
「这份文案合不合规」由独立的 reviewer agent 判定，本文件两者都不碰。

失败语义：任何异常都不抛给调用方。文案或主图失败会 `mark_failed`（该平台整体失败，
由主控决定是重试、跳过还是降级交付）；详情图与视频失败只记 open_issues，
因为那只影响丰富度，不影响可上架。
"""
from __future__ import annotations

import logging

from ...bailian.client import BailianLike
from ...schemas import GenerateRequest, PlatformListing, Understanding
from ..copywriting import CopywritingAgent
from ..rules_engine import RulesEngineAgent
from ..visual import VisualAgent
from .blackboard import Blackboard

logger = logging.getLogger(__name__)


class PlatformWorker:
    """单平台执行者：调用文案 / 视觉 agent 干活，并把版本变更写回黑板。

    黑板上的版本号是审核失效的唯一依据，所以每改一次产物都必须调用对应的 mark_*——
    漏调一次就会出现「改过文案却仍宣称已审核」的错误状态。
    """

    def __init__(
        self,
        client: BailianLike,
        copy_agent: CopywritingAgent,
        visual_agent: VisualAgent,
        rules_agent: RulesEngineAgent,
    ) -> None:
        self.client = client
        self.copy_agent = copy_agent
        self.visual_agent = visual_agent
        self.rules_agent = rules_agent

    # ------------------------------------------------------------------ 文案

    async def run_copy(
        self,
        bb: Blackboard,
        req: GenerateRequest,
        platform: str,
        focus: str = "",
    ) -> PlatformListing | None:
        """生成该平台文案并写回黑板，返回生成的 PlatformListing。

        失败时：调用 `bb.mark_failed` 后返回 None（不抛异常），由主控决定整体走向。
        因此调用方必须判空，不能直接解引用返回值。

        `focus` 是主控给的生成要点（如「突出材质」「面向母婴人群」），原样透传给文案 agent。
        """
        try:
            rules = self._ensure_rules(bb, platform)
            understanding = self._require_understanding(bb)
            listing = await self.copy_agent.run(req, understanding, platform, rules, focus=focus)
            # 文案版本 +1 会让此前所有审核结论自动作废——这是唯一入口，不能省。
            bb.mark_copy(platform, display_name=listing.display_name or rules.get("displayName", ""))
            return listing
        except Exception as exc:  # noqa: BLE001 —— 单平台失败只影响该平台，不能冒泡打断整批
            logger.warning("平台 %s 文案生成失败: %s", platform, exc)
            bb.mark_failed(platform, f"{type(exc).__name__}: {exc}")
            return None

    # ------------------------------------------------------------------ 视觉

    async def run_visual(
        self,
        bb: Blackboard,
        listing: PlatformListing,
        platform: str,
        image_ref: str | None = None,
        *,
        with_detail: bool = True,
        with_video: bool = True,
    ) -> None:
        """生成视觉素材并原地写回 listing：主图（必须）、详情图与视频（可选）。

        本方法不返回产物（都直接改在 listing 上）；是否成功看黑板上的 image_version / video_version。
        主图失败 = 该平台失败（mark_failed）；详情图与视频失败只降级，记 open_issues 后继续。
        """
        try:
            rules = self._ensure_rules(bb, platform)
            understanding = self._require_understanding(bb)
            await self.visual_agent.run(understanding, listing, rules, image_ref)
            if not listing.images:
                raise RuntimeError("主图未生成（视觉 agent 未返回任何图片）")
            bb.mark_images(platform)
        except Exception as exc:  # noqa: BLE001 —— 同上，单平台失败不外抛
            logger.warning("平台 %s 主图生成失败: %s", platform, exc)
            bb.mark_failed(platform, f"{type(exc).__name__}: {exc}")
            return

        # 以下两项只影响丰富度：失败不 mark_failed，否则会把一个可上架的包判成失败。
        if with_detail:
            await self._try_detail_shots(bb, listing, platform, understanding, image_ref)
        if with_video:
            await self._try_video(bb, listing, platform, understanding)

    # ------------------------------------------------------------------ 内部

    def _ensure_rules(self, bb: Blackboard, platform: str) -> dict:
        """保证 bb.rules 里有该平台规则：缺失时用规则引擎补上并写回黑板。

        规则引擎是同步方法且只做本地读取，直接调用不占用事件循环；
        只补当前平台，动到 bb.rules 也不影响其他平台已有的规则。
        """
        rules = bb.rules.get(platform)
        if not rules:
            rules = self.rules_agent.run([platform]).get(platform) or {}
            if rules:
                bb.rules[platform] = rules
        return rules

    @staticmethod
    def _require_understanding(bb: Blackboard) -> Understanding:
        """取商品理解结果；没准备好就抛错（调用方负责 mark_failed）。

        文案与视觉都强依赖商品理解，缺了它生成出来的东西毫无意义，
        所以这里硬失败，而不是让下游模型去猜。
        """
        understanding = bb.understanding
        if understanding is None:
            raise RuntimeError("understanding 未就绪，无法生成（前置条件应为 understanding.ready）")
        return understanding

    async def _try_detail_shots(
        self,
        bb: Blackboard,
        listing: PlatformListing,
        platform: str,
        understanding: Understanding,
        image_ref: str | None,
    ) -> None:
        """生成详情图；失败只记 open_issues，不影响该平台的可上架判定。"""
        try:
            await self.visual_agent.run_detail_shots(understanding, listing, image_ref)
        except Exception as exc:  # noqa: BLE001 —— 详情图是锦上添花，失败不该拖垮整个平台
            logger.warning("平台 %s 详情图生成失败: %s", platform, exc)
            bb.open_issues.append(f"{platform}: 详情图生成失败（{type(exc).__name__}: {exc}）")

    async def _try_video(
        self,
        bb: Blackboard,
        listing: PlatformListing,
        platform: str,
        understanding: Understanding,
    ) -> None:
        """生成展示视频；失败或无产物只记 open_issues，成功才 mark_video。

        视觉 agent 内部已吞掉生成异常（video_url 保持 None），
        所以除异常外还要按产物是否存在来决定是否标记版本。
        """
        try:
            await self.visual_agent.run_video(understanding, listing)
        except Exception as exc:  # noqa: BLE001 —— 视频是加分项，失败不影响上架
            logger.warning("平台 %s 视频生成失败: %s", platform, exc)
            bb.open_issues.append(f"{platform}: 视频生成失败（{type(exc).__name__}: {exc}）")
            return
        if listing.video_url:
            bb.mark_video(platform)
