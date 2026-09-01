"""选品灵感 Skill 实现 — 市场 + 类目 → 3 条数据驱动的选品建议。"""
from __future__ import annotations

import asyncio
import json
import logging
import re
from typing import Any

from ..prompts import load as load_prompt

logger = logging.getLogger(__name__)

MARKETS = {
    "us": "美国市场（Amazon 为主，客单价中高，重视合规与品牌感）",
    "sea": "东南亚市场（Shopee / Lazada / TikTok Shop，价格敏感、内容种草强）",
    "global": "全球市场（AliExpress，高性价比，多语言多地区）",
}

CATEGORIES = {
    "electronics": "3C / 小家电",
    "home_kitchen": "家居 / 厨房用品",
    "apparel": "服饰 / 配饰",
}

MOCK_SUGGESTIONS = {
    "electronics": [
        ("迷你挂脖风扇 4000mAh", "夏季户外通勤刚需，轻小件物流友好", "三档风力；续航 8 小时；仅 230g", "electronics"),
        ("桌面加湿器 300ml 静音版", "秋冬家居小家电复购率高", "静音 30dB；USB 供电；自动断电保护", "electronics"),
        ("便携挂烫机 800W 可折叠", "差旅人群增长快，差异化明显", "15 秒预热；可折叠收纳；干湿两用", "electronics"),
    ],
    "home_kitchen": [
        ("硅胶折叠水杯 550ml", "户外露营热度持续，轻便好寄", "食品级硅胶；折叠后仅 6cm；防漏设计", "home_kitchen"),
        ("厨房多功能削皮器三合一", "高频低价引流款，转化率高", "三合一刀头；防滑握柄；可挂墙收纳", "home_kitchen"),
        ("桌面收纳盒三件套 透明", "居家办公场景需求稳定", "模块化组合；防尘带盖；易清洁", "home_kitchen"),
    ],
    "apparel": [
        ("冰袖防晒袖套 UPF50+ 两双装", "夏季户外配件，尺码压力小", "UPF50+；冰感面料；防滑不卷边", "apparel"),
        ("运动腰包 6.5 英寸防水款", "跑步骑行人群稳定复购", "防水面料；触屏可视；反光条设计", "apparel"),
        ("可折叠渔夫帽 透气款", "轻量配饰，退货率低", "可折叠收纳；透气网眼；多色可选", "apparel"),
    ],
}


class IdeationSkill:
    """根据市场 + 类目 → 3 条差异化选品建议。"""

    def __init__(self, config: dict | None = None, mock: bool | None = None) -> None:
        self.config = config or {}
        if mock is not None:
            self.config["mock"] = mock
        self.mock_mode = self.config.get("mock", False)

    async def run(
        self,
        market: str = "global",
        category: str = "home_kitchen",
        trends: list[str] | None = None,
        competitor_band: dict | None = None,
    ) -> dict[str, Any]:
        """主入口：生成选品建议。

        Args:
            market: 目标市场 (us / sea / global)
            category: 类目 (electronics / home_kitchen / apparel)
            trends: 实时热搜词列表（可选）
            competitor_band: 竞品价格带（可选）

        Returns:
            {suggestions: [...], trend_source, competitor_band_source}
        """
        market = market if market in MARKETS else "global"
        category = category if category in CATEGORIES else "home_kitchen"
        trend_source = "mock" if self.mock_mode else "mock"
        band_source = "mock" if self.mock_mode else "mock"

        if self.mock_mode:
            suggestions = self._mock(category, trends)
        else:
            client = self.config.get("client")
            if client:
                suggestions = await self._generate(client, market, category, trends)
            else:
                suggestions = self._mock(category, trends)

        return {
            "market": market,
            "suggestions": suggestions,
            "trend_source": trend_source,
            "competitor_band": competitor_band,
            "competitor_band_source": band_source,
        }

    def _mock(self, category: str, trends: list | None = None) -> list[dict[str, str]]:
        """Mock 模式：返回确定性示例建议。"""
        entries = MOCK_SUGGESTIONS.get(category, MOCK_SUGGESTIONS["home_kitchen"])
        return [
            {
                "product_name": n,
                "reason": f"{t}（{cat}热销方向）" if trends else t,
                "selling_points": s,
                "category": c,
            }
            for n, t, s, c in entries
        ]

    async def _generate(self, client: Any, market: str, category: str, trends: list | None) -> list[dict]:
        """LLM 生成模式。"""
        system = load_prompt("ideation_system") or self._default_system()
        trend_block = f"\n近期热搜：{'、'.join(trends[:8])}\n请优先贴合热搜趋势。" if trends else ""
        user = f"目标市场：{MARKETS[market]}\n类目方向：{CATEGORIES.get(category, category)}{trend_block}\n请给出 3 条选品建议。"
        try:
            raw = await asyncio.to_thread(client.chat, system, user)
            return self._parse(raw, category)
        except Exception as exc:
            logger.warning("选品建议 LLM 生成失败，降级 mock: %s", exc)
            return self._mock(category, trends)

    def _parse(self, raw: str, fallback_category: str) -> list[dict]:
        match = re.search(r"\{.*\}", raw, re.DOTALL)
        if not match:
            raise ValueError(f"选品建议输出无法解析: {raw[:200]}")
        data = json.loads(match.group(0))
        result = []
        for item in data.get("suggestions", [])[:3]:
            if not item.get("product_name"):
                continue
            result.append({
                "product_name": str(item["product_name"]).strip(),
                "reason": str(item.get("reason", "")).strip(),
                "selling_points": str(item.get("selling_points", "")).strip(),
                "category": item.get("category") or fallback_category,
            })
        if not result:
            raise ValueError("选品建议为空")
        return result

    def _default_system(self) -> str:
        return (
            "你是跨境电商选品专家。根据目标市场与类目，给出 3 个具体可落地的商品建议。"
            "输出严格 JSON：{\"suggestions\": [{\"product_name\": \"...\", \"reason\": \"...\", "
            "\"selling_points\": \"...\", \"category\": \"...\"}]}"
        )


__all__ = ["IdeationSkill"]
