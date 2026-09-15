"""规则库加载器：rules/*.json 是唯一事实来源，规则引擎直接消费。

已安装技能（skill_store）的规则补丁以 overlay 形式在读取时合并：
只追加（禁词词组 / 检查项），不改源文件；安装/卸载后调 cache_clear() 失效。
"""
from __future__ import annotations

import json
from functools import lru_cache

from .paths import readonly_dir

RULES_DIR = readonly_dir("rules")


def _with_overlay(platform: str, rules: dict) -> dict:
    from . import skill_store

    patch = skill_store.rules_patch(platform)
    if not patch:
        return rules
    merged = json.loads(json.dumps(rules))  # 深拷贝，避免污染 lru_cache 里的原件
    for group, words in patch.get("bannedWords", {}).items():
        existing = merged.setdefault("bannedWords", {}).setdefault(group, [])
        existing.extend(w for w in words if w not in existing)
    merged.setdefault("complianceChecks", []).extend(patch.get("complianceChecks", []))
    return merged


@lru_cache(maxsize=None)
def load_rules(platform: str) -> dict:
    path = RULES_DIR / f"{platform}.json"
    if not path.exists():
        raise FileNotFoundError(f"未找到平台规则库: {path}")
    return _with_overlay(platform, json.loads(path.read_text(encoding="utf-8")))


def all_platforms() -> dict[str, dict]:
    rules: dict[str, dict] = {}
    for path in sorted(RULES_DIR.glob("*.json")):
        data = json.loads(path.read_text(encoding="utf-8"))
        rules[data["platform"]] = _with_overlay(data["platform"], data)
    return rules


def cache_clear() -> None:
    load_rules.cache_clear()
