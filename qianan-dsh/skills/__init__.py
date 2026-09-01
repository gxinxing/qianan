"""千岸 DSH Skills 共享工具库。

规则加载、overlay 合并、缓存管理 — 被所有 skill 公共使用。
"""
from __future__ import annotations

import json
import logging
from functools import lru_cache
from pathlib import Path

logger = logging.getLogger(__name__)

RULES_DIR = Path(__file__).resolve().parent.parent / "data" / "rules"
SKILLS_INSTALLED_DIR = Path(__file__).resolve().parent.parent / "data" / "skills" / "installed"


@lru_cache(maxsize=None)
def load_rules(platform: str) -> dict:
    """加载平台规则 JSON（含已安装技能 overlay 补丁）。"""
    path = RULES_DIR / f"{platform}.json"
    if not path.exists():
        raise FileNotFoundError(f"未找到平台规则: {path}")
    data = json.loads(path.read_text(encoding="utf-8"))
    return _with_overlay(platform, data)


def all_platforms() -> dict[str, dict]:
    """加载所有平台规则（按版本号降序排序）。"""
    rules: dict[str, dict] = {}
    for path in sorted(RULES_DIR.glob("*.json")):
        data = json.loads(path.read_text(encoding="utf-8"))
        key = data.get("platform", path.stem)
        rules[key] = load_rules(key)
    return rules


def _with_overlay(platform: str, rules: dict) -> dict:
    """以 overlay 形式合并已安装技能的规则补丁（只追加不改源文件）。"""
    overlay_path = SKILLS_INSTALLED_DIR / f"{platform}.json"
    if not overlay_path.exists():
        return rules
    try:
        patch = json.loads(overlay_path.read_text(encoding="utf-8"))
    except Exception:
        return rules
    merged = json.loads(json.dumps(rules))  # deep copy
    for group, words in patch.get("bannedWords", {}).items():
        existing = merged.setdefault("bannedWords", {}).setdefault(group, [])
        existing.extend(w for w in words if w not in existing)
    for check in patch.get("complianceChecks", []):
        merged.setdefault("complianceChecks", []).append(check)
    return merged


def constraint_brief(rules: dict) -> str:
    """把完整规则压缩成给 LLM 的自然语言约束片段。"""
    parts: list[str] = []
    title = rules.get("title", {})
    if title:
        parts.append(f"标题 ≤{title.get('maxLength')} 字符，公式：{title.get('formula', '')}")
    bullets = rules.get("bullets")
    if bullets:
        parts.append(f"五点描述 {bullets.get('count')} 条，每条 ≤{bullets.get('maxLengthPer')} 字符")
    desc = rules.get("description", {})
    if desc.get("maxLength"):
        parts.append(f"描述 ≤{desc['maxLength']} 字符")
    banned = rules.get("bannedWords", {})
    words = [w for group in banned.values() if isinstance(group, list) for w in group]
    if words:
        parts.append("禁止使用以下词语：" + ", ".join(words[:30]))
    return "；".join(parts)


def cache_clear() -> None:
    """规则缓存失效（技能安装/卸载/更新后调用）。"""
    load_rules.cache_clear()
