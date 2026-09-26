"""Agent 自动识别与 MCP 挂载测试。"""
from __future__ import annotations

from app.installer import install_all


def test_install_all_agents():
    installed = install_all()
    assert isinstance(installed, list)
