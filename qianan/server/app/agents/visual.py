"""④ 视觉 Agent：以图改图优先（上传商品照 → 平台合规主图），失败回退纯文生图。

以图改图方案对齐 qianwen-agent（出海竞赛 87.82 分同款）：
把卖家上传的真实商品照作为参考图，提示词锁定"保持商品本体不变，
只按平台规范改写背景/构图"，产出照片级质感的主图。
"""
from __future__ import annotations

import asyncio
import logging

from ..bailian.client import BailianLike
from ..schemas import PlatformListing, Understanding

logger = logging.getLogger(__name__)

REF_PROMPT = """Reference image 1 (图1) is the real product photo. Keep the exact same product (shape, color, pattern, material, every detail) — do NOT redesign or reimagine it.
基于这张真实商品照生成电商主图：
商品：{product}
平台主图规范：{image_rules}
要求：保持商品本体与照片完全一致，仅按规范调整背景与构图；电商级布光，主体居中占画面 85% 以上，无水印、无边框、无文字，商业摄影质感。"""

TEXT_PROMPT = """为电商主图生成一张高质量商品场景图：
商品：{product}
卖点：{points}
平台主图规范：{image_rules}
要求：电商级构图，干净背景，主体居中占画面 85% 以上，无水印、无边框、无文字，商业摄影质感。"""


class VisualAgent:
    def __init__(self, client: BailianLike) -> None:
        self.client = client

    async def run(
        self,
        understanding: Understanding,
        listing: PlatformListing,
        rules: dict,
        image_ref: str | None = None,
    ) -> None:
        """为单个平台上架包生成主图，URL 写回 listing.images。

        有上传图（image_ref）时优先以图改图；失败（如参考图不可用）回退纯文生图。
        """
        image_rules = _image_brief(rules)
        if self.client.is_mock:
            listing.images.append(f"mock://image/{listing.platform}.jpg")
            return

        if image_ref:
            ref_prompt = REF_PROMPT.format(
                product=understanding.product_type or "product",
                image_rules=image_rules or "白底、主体突出",
            )
            try:
                url = await asyncio.to_thread(self.client.image_gen, ref_prompt, None, image_ref)
                listing.images.append(url)
                return
            except Exception as exc:  # noqa: BLE001 —— 参考图模式失败时回退纯文生图
                logger.warning("以图改图失败（%s），回退纯文生图: %s", listing.platform, exc)

        text_prompt = TEXT_PROMPT.format(
            product=understanding.product_type or "product",
            points="; ".join(understanding.selling_points[:3]) or "high quality",
            image_rules=image_rules or "白底、主体突出",
        )
        try:
            url = await asyncio.to_thread(self.client.image_gen, text_prompt)
            listing.images.append(url)
            return
        except Exception as exc:  # noqa: BLE001 —— 文生图也失败时用原图兜底，保证交付物永远有主图
            logger.warning("文生图也失败（%s），回退原图占位: %s", listing.platform, exc)
            if image_ref:
                listing.images.append(image_ref)
                return
            raise


def _image_brief(rules: dict) -> str:
    """把平台主图规范转成给文生图模型的简要约束。"""
    main = rules.get("mainImage", {})
    parts = []
    bg = main.get("background")
    if bg == "white":
        parts.append("纯白背景")
    elif bg == "clean":
        parts.append("干净简洁背景")
    if main.get("noText"):
        parts.append("画面不含文字")
    if main.get("noWatermark"):
        parts.append("无水印")
    return "，".join(parts)
