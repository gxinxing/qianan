"""视觉生成 Skill 实现 — 平台规范主图生成（以图改图优先 → 纯文生图回退）。

调用方需自行处理 API 鉴权——本 skill 只组装 prompt 和图片 URL。
实际百炼 API 调用通过 client.image_gen() 委托给调用方传入的 client。
"""
from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)


class VisualAgentSkill:
    """为每个平台生成符合规范的商品主图 URL。"""

    PLATFORM_SPECS = {
        "amazon":      {"size": "1000x1000", "bg": "pure white", "fill": 0.85},
        "shopee":      {"size": "800x800",   "bg": "clean light",  "fill": 0.80},
        "aliexpress":  {"size": "800x800",   "bg": "white",        "fill": 0.80},
        "lazada":      {"size": "500x500",   "bg": "white",        "fill": 0.75},
        "tiktokshop":  {"size": "1080x1080", "bg": "solid color",  "fill": 0.70},
    }

    def __init__(self, config: dict | None = None, mock: bool | None = None) -> None:
        self.config = config or {}
        if mock is not None:
            self.config["mock"] = mock
        self.mock_mode = self.config.get("mock", False)

    async def run(
        self,
        understanding: dict[str, Any],
        listing: dict[str, Any],
        rules: dict[str, Any],
        image_ref: str | None = None,
    ) -> dict[str, Any]:
        """为单平台上架包生成主图。

        Args:
            understanding: 商品理解结果
            listing: 当前 Listing（会写入生成的图片 URL）
            rules: 平台规则
            image_ref: 卖家上传的参考图 URL / base64

        Returns:
            {platform, images: [urls], primary_url, generation_type, fallback_used}
        """
        platform = listing.get("platform", rules.get("platform", "unknown"))
        spec = self.PLATFORM_SPECS.get(platform, self.PLATFORM_SPECS["amazon"])
        client = self.config.get("client")
        use_canned = self.config.get("use_canned_images", False)
        use_text2img = self.config.get("text2img_fallback", False)

        generation_type = "mock" if self.mock_mode or not client else "text2img"

        if self.mock_mode or not client or use_canned:
            urls = self._mock_image_urls(platform, count=1)
        elif image_ref:
            # 以图改图 (img2img) 优先
            try:
                urls = [await self._img2img(client, image_ref, understanding, spec)]
                generation_type = "img2img"
            except Exception as exc:
                logger.warning("以图改图失败，回退文生图: %s", exc)
                if use_text2img:
                    urls = [await self._text2img(client, understanding, spec)]
                    generation_type = "text2img"
                else:
                    urls = self._mock_image_urls(platform, count=1)
                    generation_type = "mock"
        else:
            # 纯文生图
            if use_text2img:
                urls = [await self._text2img(client, understanding, spec)]
                generation_type = "text2img"
            else:
                urls = self._mock_image_urls(platform, count=1)
                generation_type = "mock"

        listing.setdefault("images", []).extend(urls)
        return {
            "platform": platform,
            "images": urls,
            "primary_url": urls[0] if urls else "",
            "generation_type": generation_type,
            "fallback_used": generation_type == "mock" and not self.mock_mode,
        }

    def build_prompts(self, understanding: dict, spec: dict) -> tuple[str, str]:
        """构建 img2img 和 text2img 的 prompt（供调用方参考）。"""
        product = understanding.get("product_type", "the product")
        points = ", ".join(understanding.get("selling_points", [])[:3])
        rules_str = (
            f"{spec['size']}px, {spec['bg']} background, "
            f"product fills {spec['fill']*100:.0f}% of frame, "
            "no watermark, no text, no border, commercial photography"
        )
        img2img = (
            f"Reference image 1 is the real product photo. Keep the exact same product "
            f"(shape, color, pattern, material) — do NOT redesign it.\n"
            f"基于这张真实商品照生成电商主图：产品 {product}，卖点 {points}。"
            f"平台规范：{rules_str}。保持商品本体与照片完全一致，仅调整背景与构图。"
        )
        text2img = (
            f"为电商主图生成高质量商品场景图：产品 {product}，卖点 {points}。"
            f"平台规范：{rules_str}。电商级构图，干净背景，主体居中。"
        )
        return img2img, text2img

    async def _img2img(self, client: Any, image_ref: str, understanding: dict, spec: dict) -> str:
        prompt, _ = self.build_prompts(understanding, spec)
        return await asyncio.to_thread(client.image_gen, prompt, ref_image=image_ref)

    async def _text2img(self, client: Any, understanding: dict, spec: dict) -> str:
        _, prompt = self.build_prompts(understanding, spec)
        return await asyncio.to_thread(client.image_gen, prompt)

    def _mock_image_urls(self, platform: str, count: int = 1) -> list[str]:
        base = f"mock://image/{platform}"
        return [f"{base}_{i + 1}.jpg" for i in range(count)]


__all__ = ["VisualAgentSkill"]
