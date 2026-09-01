"""商品理解 Skill 实现 — 将卖家原始输入结构化为商品档案。

优先尝试视觉理解（VL），不可用时回退纯文本 LLM，全部失败走 mock 模式。
"""
from __future__ import annotations

import asyncio
import logging
import re
from typing import Any

logger = logging.getLogger(__name__)

SYSTEM_TEMPLATE = """你是跨境电商商品分析专家。根据卖家提供的商品信息，输出严格的 JSON（不要 markdown 代码块、不要多余文字）：
{{
  "category": "商品类目，从 electronics / home_kitchen / apparel 中选一个",
  "product_type": "产品类型（英文短语，如 portable blender）",
  "material": "主要材质（英文，未知则留空字符串）",
  "attributes": {{"关键属性": "值"}},
  "selling_points": ["英文卖点1", "英文卖点2", "英文卖点3"],
  "target_audience": "目标受众（英文）",
  "keywords": ["核心搜索关键词（英文，5-8个）"]
}}"""

TEXT_PROMPT_TEMPLATE = """商品名称：{product_name}
卖家描述类目：{category}
中文卖点描述：{selling_points}

请基于以上信息推断并输出 JSON。"""

VISION_PROMPT_TEMPLATE = """商品卖点（卖家描述）：{selling_points}

请结合商品图片和卖点描述，输出 JSON。"""


class ProductUnderstandingSkill:
    """将卖家输入（商品图 + 卖点文本）转化为结构化商品档案。"""

    def __init__(self, config: dict | None = None, mock: bool | None = None) -> None:
        self.config = config or {}
        if mock is not None:
            self.config["mock"] = mock
        self.mock_mode = self.config.get("mock", False)

    async def run(
        self,
        product_name: str = "",
        selling_points: str = "",
        category: str = "home_kitchen",
        image_url: str = "",
        image_base64: str = "",
        **_kwargs: Any,
    ) -> dict[str, Any]:
        """主入口：结构化解析商品信息。

        Args:
            product_name: 商品名称
            selling_points: 中文卖点描述
            category: 用户选择的类目
            image_url: 商品图公网 URL
            image_base64: 商品图 base64 data URI

        Returns:
            Understanding dict with category / product_type / material / ...
        """
        if self.mock_mode:
            return self._mock(product_name, selling_points, category)

        client = self.config.get("client")
        if client and (image_url or image_base64):
            try:
                return await self._vision_path(client, product_name, selling_points, category, image_url or image_base64)
            except Exception as exc:
                logger.warning("视觉理解失败，回退文本路径: %s", exc)

        if client:
            return await self._text_path(client, product_name, selling_points, category)

        return self._mock(product_name, selling_points, category)

    async def _text_path(self, client: Any, name: str, points: str, cat: str) -> dict[str, Any]:
        """纯文本路径：LLM 生成结构化理解。"""
        from ..prompts import load as load_prompt
        system = load_prompt("understanding_system") or SYSTEM_TEMPLATE
        user = TEXT_PROMPT_TEMPLATE.format(
            product_name=name or "unknown",
            category=cat,
            selling_points=points or "无描述",
        )
        raw = await asyncio.to_thread(client.chat, system, user)
        return self._parse(raw, cat)

    async def _vision_path(self, client: Any, name: str, points: str, cat: str, img: str) -> dict[str, Any]:
        """视觉路径：VL 模型理解商品图。"""
        vision_model = self.config.get("vision_model")
        if not vision_model:
            raise RuntimeError("未配置 VL 模型，无法使用视觉理解")
        from ..prompts import load as load_prompt
        system = load_prompt("understanding_system") or SYSTEM_TEMPLATE
        user = VISION_PROMPT_TEMPLATE.format(selling_points=points or "无描述")
        raw = await asyncio.to_thread(client.vision, img, user, model=vision_model)
        return self._parse(raw, cat)

    def _parse(self, raw: str, fallback_category: str) -> dict[str, Any]:
        """从 LLM 输出提取 JSON。"""
        match = re.search(r"\{.*\}", raw, re.DOTALL)
        if not match:
            raise ValueError(f"商品理解输出无法解析: {raw[:200]}")
        data = json.loads(match.group(0))
        data.setdefault("category", fallback_category)
        return data

    def _mock(self, name: str, points: str, cat: str) -> dict[str, Any]:
        """Mock 模式：基于输入做确定性解析。"""
        name = name or "Unknown Product"
        sp_list = [s.strip() for s in re.split(r"[；;。\n,]+", points) if s.strip()][:5]
        if not sp_list and points:
            sp_list = [points[:50]]
        keywords = [w.lower() for w in re.split(r"\s+", name) if len(w) > 1][:6]
        if len(keywords) < 3:
            keywords.extend(["quality", "premium", "portable"])
        return {
            "category": cat,
            "product_type": name.lower(),
            "material": "ABS + stainless steel",
            "attributes": {"品牌": "示例品牌", "颜色": "White"},
            "selling_points": sp_list or ["premium quality", "durable design", "easy to use"],
            "target_audience": "young urban consumers",
            "keywords": keywords[:8],
        }


__all__ = ["ProductUnderstandingSkill"]
