"""电商运营洞察与竞品痛点反切引擎。

从 rules/insights/complaints.json 加载各类目的 Top 消费者差评痛点与反切标签；
为文案 Agent 与运营规划提供针对性防御策略（Pain-point Antidote）。
"""
from __future__ import annotations

import json
from functools import lru_cache
from typing import Any

from ..paths import readonly_dir

INSIGHTS_DIR = readonly_dir("rules", "insights")
COMPLAINTS_FILE = INSIGHTS_DIR / "complaints.json"


@lru_cache(maxsize=1)
def load_complaints_data() -> dict[str, Any]:
    if COMPLAINTS_FILE.exists():
        try:
            return json.loads(COMPLAINTS_FILE.read_text(encoding="utf-8"))
        except Exception:
            pass
    return {"categories": {}}


def get_category_complaints(category: str) -> list[dict[str, Any]]:
    """获取指定品类的竞品痛点列表，支持泛化回退到 general 通用类别。"""
    data = load_complaints_data()
    categories = data.get("categories", {})
    if category in categories and categories[category].get("top_complaints"):
        return categories[category]["top_complaints"]
    # 模糊匹配
    cat_lower = category.lower()
    for k, v in categories.items():
        if k in cat_lower or cat_lower in k:
            if v.get("top_complaints"):
                return v["top_complaints"]
    return categories.get("general", {}).get("top_complaints", [])


def format_complaints_brief(category: str, limit: int = 3) -> str:
    """生成供提示词注入的竞品痛点反切策略指导文本。"""
    complaints = get_category_complaints(category)[:limit]
    if not complaints:
        return ""
    lines = ["【竞品常见痛点与反切策略（五点前三条务必进行痛点反打防御，杜绝空泛吹嘘）】："]
    for i, c in enumerate(complaints, 1):
        lines.append(
            f"{i}. 针对竞品痛点『{c.get('complaint')}』→ 建议标签 [{c.get('counter_tag')}]："
            f" 突出解决策略：{c.get('suggested_antidote')}"
        )
    return "\n".join(lines)
