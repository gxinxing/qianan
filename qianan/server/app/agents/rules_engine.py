"""② 规则引擎（非 LLM）：读取规则库，为每个平台产出约束清单。

这是千岸的护城河：结构化规则 + 确定性逻辑，不用 LLM，不产生幻觉。
"""
from __future__ import annotations

from ..rules_store import load_rules


class RulesEngineAgent:
    def run(self, platforms: list[str]) -> dict[str, dict]:
        return {platform: load_rules(platform) for platform in platforms}

    @staticmethod
    def constraint_brief(rules: dict) -> str:
        """把规则压缩成给文案 Agent 的自然语言约束（拼进 prompt）。"""
        parts: list[str] = []
        title = rules.get("title", {})
        if title:
            parts.append(f"标题 ≤{title.get('maxLength')} 字符，公式：{title.get('formula', '')}")
        # 仅对使用 bullet points 的平台（Amazon）添加约束；其余平台用 description
        bullets = rules.get("bullets")
        if bullets and bullets.get("style") != "none":
            parts.append(
                f"五点描述 {bullets.get('count', 5)} 条，每条 ≤{bullets.get('maxLengthPer', 500)} 字符"
            )
        desc = rules.get("description", {})
        if desc.get("maxLength"):
            parts.append(f"描述 ≤{desc['maxLength']} 字符")
        banned = rules.get("bannedWords", {})
        words = [w for group in banned.values() if isinstance(group, list) for w in group]
        if words:
            parts.append("禁止使用以下词语：" + ", ".join(words[:30]))
        return "；".join(parts)
