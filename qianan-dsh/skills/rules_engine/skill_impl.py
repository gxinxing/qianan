"""规则引擎 Skill 实现 — 确定性 JSON 规则库加载与约束提取。

不使用 LLM — 这是千岸的护城河。
"""
from __future__ import annotations

import logging
from typing import Any

from .. import load_rules, all_platforms, constraint_brief

logger = logging.getLogger(__name__)


class RulesEngineSkill:
    """为选中的每个平台加载结构化规则 JSON，输出约束清单。"""

    SUPPORTED_PLATFORMS = ["amazon", "shopee", "aliexpress", "lazada", "tiktokshop"]

    def __init__(self, config: dict | None = None, mock: bool | None = None) -> None:
        self.config = config or {}
        if mock is not None:
            self.config["mock"] = mock
        self.mock_mode = self.config.get("mock", False)

    async def run(
        self,
        platforms: list[str] | None = None,
        category: str = "home_kitchen",
    ) -> dict[str, dict]:
        """加载指定平台的规则（去重 + 校验）。

        Args:
            platforms: 平台 key 列表，默认全部 5 个
            category: 商品类目（用于校验分类属性规则存在性）

        Returns:
            {platform_key: rules_dict} 映射表
        """
        if not platforms:
            platforms = self.SUPPORTED_PLATFORMS
        unknown = [p for p in platforms if p not in self.SUPPORTED_PLATFORMS]
        if unknown:
            logger.warning("未知平台（将被跳过）: %s", unknown)
        result: dict[str, dict] = {}
        for platform in platforms:
            if platform not in self.SUPPORTED_PLATFORMS:
                continue
            try:
                rules = load_rules(platform)
                result[platform] = rules
                logger.debug("规则加载 [%s] OK", platform)
            except FileNotFoundError:
                logger.error("规则文件缺失: %s", platform)
                continue
        return result

    def constraint_brief_for(self, platform: str) -> str:
        """为指定平台生成 LLM prompt 友好的约束摘要。"""
        try:
            rules = load_rules(platform)
            return constraint_brief(rules)
        except FileNotFoundError:
            return f"平台 {platform} 规则暂不可用"

    def get_platform_info(self, platform: str) -> dict[str, Any]:
        """提取平台摘要信息（用于前端展示）。"""
        try:
            rules = load_rules(platform)
        except FileNotFoundError:
            return {"platform": platform, "available": False}
        return {
            "platform": platform,
            "available": True,
            "display_name": rules.get("displayName", platform),
            "demo_depth": rules.get("demoDepth", "unknown"),
            "locales": rules.get("locales", []),
            "title_max": rules.get("title", {}).get("maxLength"),
            "bullets_count": rules.get("bullets", {}).get("count"),
            "desc_max": rules.get("description", {}).get("maxLength"),
            "img_min": rules.get("mainImage", {}).get("minWidth"),
        }

    def list_available_platforms(self) -> list[dict[str, Any]]:
        """列出所有可用平台规则及其摘要。"""
        return [self.get_platform_info(p) for p in self.SUPPORTED_PLATFORMS]


__all__ = ["RulesEngineSkill"]
