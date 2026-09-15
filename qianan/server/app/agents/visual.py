"""④ 视觉 Agent：以图改图优先 → 多详情图 → 图生视频，三级物料闭环。

以图改图方案对齐 qianwen-agent（出海竞赛 87.82 分同款）：
把卖家上传的真实商品照作为参考图，提示词锁定"保持商品本体不变，
只按平台规范改写背景/构图"，产出照片级质感的主图。

新增能力：
- 多详情图：面料特写 / 正面全貌 / 上身场景 / 平铺搭配（以图改图，保持商品一致）
- 图生视频：基于主图调用 wan2.7-i2v 生成 5 秒展示视频
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

#: 详情图规格（对标 mzsleep 六图方案，精简为 4 张核心详情图）
DETAIL_SHOTS = [
    (
        "front_view",
        "正面全貌展示",
        "Reference image 1 (图1) is the real product photo. Generate a full front view of this product on a clean light-gray studio background. Show the complete product clearly. Keep the exact same product — shape, color, material, every detail.",
    ),
    (
        "fabric_closeup",
        "面料材质特写",
        "Reference image 1 (图1) is the real product photo. Generate a close-up macro shot focusing on the material texture and surface details of this product. Studio lighting highlighting fabric/material quality. Keep the exact same product.",
    ),
    (
        "lifestyle",
        "上身/使用场景",
        "Reference image 1 (图1) is the real product photo. Show this product being used in a natural lifestyle setting (person wearing or using it, home environment). Warm natural lighting, aspirational but realistic mood. Keep the exact same product design.",
    ),
    (
        "flatlay",
        "平铺搭配展示",
        "Reference image 1 (图1) is the real product photo. Create a flat-lay styling shot from above, showing this product arranged with complementary accessories on a neutral surface. Editorial styling, soft shadows. Keep the exact same product.",
    ),
]

VIDEO_PROMPT = "动态展示商品，自然光影变化，材质质感特写，360 度缓慢旋转展示，电商级商业摄影风格。"


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
            # 只填主图：详情图 / 视频分别由 run_detail_shots / run_video 负责。
            # 这里若一并预填，规划器跳过这两个动作时会看不出效果（假阴性）。
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

    async def run_detail_shots(
        self,
        understanding: Understanding,
        listing: PlatformListing,
        image_ref: str | None = None,
    ) -> None:
        """生成详情图（正面全貌/材质特写/使用场景/平铺搭配），写回 listing.detail_images。

        需要主图或原图作为参考（以图改图保持商品一致）；无参考图则跳过。

        **并发发起**：4 张图彼此独立，串行会把出图耗时叠加四倍
        （实测云端单步因此耗掉 373s，直接吃光整个 Agent 墙钟预算）。
        单张失败不影响其余；结果顺序与 DETAIL_SHOTS 一致。
        """
        if self.client.is_mock:
            if not listing.detail_images:
                listing.detail_images = [f"mock://detail/{listing.platform}_{s[0]}.jpg" for s in DETAIL_SHOTS]
            return

        ref = image_ref or (listing.images[0] if listing.images else None)
        if not ref or ref.startswith("mock://"):
            logger.info("平台 %s 无参考图，跳过详情图生成", listing.platform)
            return

        async def _one(key: str, prompt: str) -> str | None:
            """单张详情图：以图改图优先，失败退回纯文生图，都失败才放弃。"""
            try:
                return await asyncio.to_thread(self.client.image_gen, prompt, None, ref)
            except Exception as exc:  # noqa: BLE001 —— 参考图模式不可用时退文生图
                logger.warning("详情图 %s 以图改图失败（%s），回退纯文生图: %s", key, listing.platform, exc)
            try:
                return await asyncio.to_thread(self.client.image_gen, prompt)
            except Exception as exc:  # noqa: BLE001 —— 单张详情图失败不阻塞其余
                logger.warning("详情图 %s 文生图也失败（%s）: %s", key, listing.platform, exc)
                return None

        results = await asyncio.gather(
            *(_one(key, prompt) for key, _label, prompt in DETAIL_SHOTS)
        )
        listing.detail_images = [u for u in results if u]

    async def run_video(
        self,
        understanding: Understanding,
        listing: PlatformListing,
    ) -> None:
        """基于主图生成展示视频（图生视频），写回 listing.video_url。"""
        if self.client.is_mock:
            listing.video_url = f"mock://video/{listing.platform}.mp4"
            return

        main_image = listing.images[0] if listing.images else None
        if not main_image or main_image.startswith("mock://"):
            logger.info("平台 %s 无主图，跳过视频生成", listing.platform)
            return

        product_desc = understanding.product_type or "product"
        points = "; ".join(understanding.selling_points[:2]) or ""
        prompt = f"{VIDEO_PROMPT} 商品：{product_desc}。{points}"
        try:
            url = await asyncio.to_thread(self.client.video_gen, main_image, prompt)
            listing.video_url = url
        except Exception as exc:  # noqa: BLE001 —— 视频生成失败不阻塞管线
            logger.warning("视频生成失败（%s）: %s", listing.platform, exc)


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
