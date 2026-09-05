"""规则库加载器（app/rules_store.py）纯逻辑测试：真实 rules/*.json 是唯一事实来源。"""
from __future__ import annotations

from pathlib import Path

import pytest

from app import rules_store
from app.schemas import ALL_PLATFORMS


def test_rules_dir_pinned_to_server_rules():
    """规则库定位到 qianan/server/rules（相对路径注入），五个平台规则文件齐全。"""
    rules_dir = rules_store.RULES_DIR
    assert rules_dir == Path(__file__).resolve().parent.parent / "rules"
    assert rules_dir.is_dir()
    for platform in ALL_PLATFORMS:
        assert (rules_dir / f"{platform}.json").is_file(), f"缺少 {platform}.json"


def test_load_rules_all_platforms_and_unknown_raises():
    """逐平台加载真实规则 JSON：关键字段有效；未知平台抛 FileNotFoundError。"""
    for platform in ALL_PLATFORMS:
        rules = rules_store.load_rules(platform)
        assert rules["platform"] == platform
        assert isinstance(rules["title"]["maxLength"], int) and rules["title"]["maxLength"] > 0
        assert rules["complianceChecks"], f"{platform} 规则库应包含合规检查项"
        assert rules["bannedWords"], f"{platform} 规则库应包含禁用词分组"

    with pytest.raises(FileNotFoundError):
        rules_store.load_rules("no-such-platform")
