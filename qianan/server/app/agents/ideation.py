"""⓪ 选品灵感 Agent：市场 + 类目 → 3 条值得卖的商品建议。

对齐赛道一「从选品到上架，一键完成」：卖家还没确定卖什么时，
先按目标市场给出具体的选品建议（含理由与中文卖点），一键填入主表单进流水线。
"""
from __future__ import annotations

import asyncio
import json
import logging
import re

from ..bailian.client import BailianLike

logger = logging.getLogger(__name__)

MARKETS = {
    "us": "美国市场（Amazon 为主，客单价中高，重视合规与品牌感）",
    "sea": "东南亚市场（Shopee / Lazada / TikTok Shop，价格敏感、内容种草强）",
    "global": "全球市场（AliExpress，高性价比，多语言多地区）",
}

CATEGORIES = {
    "electronics": "3C / 小家电",
    "home_kitchen": "家居 / 厨房",
    "apparel": "服饰 / 配饰",
}

SYSTEM = """你是跨境电商选品专家。根据目标市场与类目，给出 3 个具体、可落地、适合中小卖家快速上架的商品建议。
要求：商品要具体到单品（不要泛泛的品类），考虑该市场的消费习惯、物流友好度（体积小/不易碎优先）与差异化空间。
输出严格的 JSON（不要 markdown 代码块、不要多余文字）：
{
  "suggestions": [
    {
      "product_name": "中文商品名（含关键规格，如：便携榨汁杯 380ml）",
      "reason": "为什么这个市场值得卖（1 句话）",
      "selling_points": "中文卖点，用分号分隔的 3-4 个短句",
      "category": "从 electronics / home_kitchen / apparel 中选一个"
    }
  ]
}"""

USER_PROMPT = """目标市场：{market}
类目方向：{category}
{trend_block}
请给出 3 条选品建议。"""

TREND_BLOCK = """近期该市场平台实时热搜：{words}
请优先贴合热搜趋势选品，并在 reason 中注明关联的热搜词。"""


class IdeationAgent:
    def __init__(self, client: BailianLike) -> None:
        self.client = client

    async def run(self, market: str, category: str, trends: list[str] | None = None) -> list[dict]:
        market = market if market in MARKETS else "global"
        category = category if category in CATEGORIES else "home_kitchen"

        if self.client.is_mock:
            return self._mock(category)

        trend_block = TREND_BLOCK.format(words="、".join(trends[:8])) if trends else ""
        raw = await asyncio.to_thread(
            self.client.chat,
            SYSTEM,
            USER_PROMPT.format(
                market=MARKETS[market], category=CATEGORIES[category], trend_block=trend_block
            ),
        )
        return self._parse(raw, category)

    def _parse(self, raw: str, fallback_category: str) -> list[dict]:
        match = re.search(r"\{.*\}", raw, re.DOTALL)
        if not match:
            raise ValueError(f"选品建议输出无法解析: {raw[:200]}")
        data = json.loads(match.group(0))
        result = []
        for item in data.get("suggestions", [])[:3]:
            if not item.get("product_name"):
                continue
            result.append(
                {
                    "product_name": str(item["product_name"]).strip(),
                    "reason": str(item.get("reason", "")).strip(),
                    "selling_points": str(item.get("selling_points", "")).strip(),
                    "category": item.get("category") or fallback_category,
                }
            )
        if not result:
            raise ValueError("选品建议为空")
        return result

    def _mock(self, category: str) -> list[dict]:
        samples = {
            "electronics": [
                ("迷你挂脖风扇 4000mAh", "夏季户外通勤刚需，轻小件物流友好", "三档风力；续航 8 小时；仅 230g", "electronics"),
                ("桌面加湿器 300ml", "秋冬家居小家电复购高", "静音 30dB；USB 供电；自动断电保护", "electronics"),
                ("便携挂烫机 800W", "差旅人群增长快，差异化明显", "15 秒预热；可折叠；干湿两用", "electronics"),
            ],
            "home_kitchen": [
                ("硅胶折叠水杯 550ml", "户外露营热度持续，轻便好寄", "食品级硅胶；折叠后仅 6cm；防漏设计", "home_kitchen"),
                ("厨房多功能削皮器", "高频低价引流款，转化率高", "三合一刀头；防滑握柄；可挂墙收纳", "home_kitchen"),
                ("桌面收纳盒三件套", "居家办公场景需求稳定", "模块化组合；防尘带盖；易清洁", "home_kitchen"),
            ],
            "apparel": [
                ("冰袖防晒袖套两双装", "夏季户外配件，尺码压力小", "UPF50+；冰感面料；防滑不卷边", "apparel"),
                ("运动腰包 6.5 英寸", "跑步骑行人群稳定复购", "防水面料；触屏可视；反光条设计", "apparel"),
                ("可折叠渔夫帽", "轻量配饰，退货率低", "可折叠收纳；透气网眼；多色可选", "apparel"),
            ],
        }
        return [
            {"product_name": n, "reason": r, "selling_points": s, "category": c}
            for n, r, s, c in samples.get(category, samples["home_kitchen"])
        ]
