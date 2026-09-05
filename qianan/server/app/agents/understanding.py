"""① 商品理解 Agent：把卖家输入结构化为商品理解。

Token Plan 网关暂无视觉理解模型，默认走纯文本路径（卖点 → 结构化理解）；
若配置了 QIANAN_VL_MODEL 且有图，则优先尝试视觉理解，失败自动回退文本。
"""
from __future__ import annotations

import asyncio
import json
import logging
import re

from ..bailian.client import BailianLike
from ..schemas import GenerateRequest, Understanding

logger = logging.getLogger(__name__)

SYSTEM = """你是跨境电商商品分析专家。根据卖家提供的商品信息，输出严格的 JSON（不要 markdown 代码块、不要多余文字）：
{
  "category": "商品类目，从 electronics / home_kitchen / apparel 中选一个",
  "product_type": "产品类型（英文短语，如 portable blender）",
  "material": "主要材质（英文，未知则留空字符串）",
  "attributes": {"关键属性": "值"},
  "selling_points": ["卖点1（英文短语）", "卖点2", "卖点3"],
  "target_audience": "目标受众（英文）",
  "keywords": ["核心搜索关键词（英文，5-8个）"]
}"""

TEXT_PROMPT = """商品名称：{product_name}
卖家描述类目：{category}
中文卖点描述：{selling_points}

请基于以上信息推断并输出 JSON。"""

VISION_PROMPT = """商品名称：{product_name}
卖家补充描述（可为空，留空则完全看图推断）：{selling_points}

请观察图片识别主体商品（忽略杂乱背景、杂物、人手等干扰），结合以上信息，严格输出 JSON（不要 markdown 代码块、不要多余文字）：
{{
  "category": "商品类目，从 electronics / home_kitchen / apparel 中选一个",
  "product_type": "产品类型（英文短语，如 portable blender）",
  "material": "主要材质（英文，未知则留空字符串）",
  "attributes": {{"关键属性": "值"}},
  "selling_points": ["卖点1（英文短语）", "卖点2", "卖点3"],
  "target_audience": "目标受众（英文）",
  "keywords": ["核心搜索关键词（英文，5-8个）"]
}}"""


class ProductUnderstandingAgent:
    def __init__(self, client: BailianLike) -> None:
        self.client = client

    async def run(self, req: GenerateRequest, image_ref: str | None = None) -> Understanding:
        if self.client.is_mock:
            return self._mock(req)

        if self.client.supports_vision and image_ref:
            try:
                raw = await asyncio.to_thread(
                    self.client.vision,
                    image_ref,
                    VISION_PROMPT.format(
                        product_name=req.product_name, selling_points=req.selling_points or "（无）"
                    ),
                )
                return self._parse(raw, req)
            except Exception as exc:  # noqa: BLE001
                logger.warning("视觉理解失败，回退纯文本路径: %s", exc)

        raw = await asyncio.to_thread(
            self.client.chat,
            SYSTEM,
            TEXT_PROMPT.format(
                product_name=req.product_name,
                category=req.category,
                selling_points=req.selling_points or "（无，请基于商品名称推断）",
            ),
        )
        return self._parse(raw, req)

    def _parse(self, raw: str, req: GenerateRequest) -> Understanding:
        data = _extract_json(raw)
        data.setdefault("category", req.category)
        return Understanding(**{k: data[k] for k in Understanding.model_fields if k in data})

    def _mock(self, req: GenerateRequest) -> Understanding:
        name = req.product_name
        return Understanding(
            category=req.category,
            product_type=name.lower(),
            material="ABS + stainless steel",
            attributes={"品牌": "示例品牌", "颜色": "白色"},
            selling_points=[s.strip() for s in re.split(r"[；;。\n]", req.selling_points) if s.strip()][:5],
            target_audience="young urban consumers",
            keywords=[w.lower() for w in name.split()][:6] or ["product"],
        )


def _extract_json(text: str) -> dict:
    """从 LLM 输出里稳健地提取 JSON。"""
    match = re.search(r"\{.*\}", text, re.DOTALL)
    if not match:
        raise ValueError(f"商品理解输出无法解析: {text[:200]}")
    return json.loads(match.group(0))
