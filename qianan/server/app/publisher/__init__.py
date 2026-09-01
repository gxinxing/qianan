"""上架执行器层（PRD v0.3 · Feature 1）。

三种实现：MockBrowserPublisher（演示主路径）/ ExtensionAssist（半自动回填）/
ComputerUse（接口占位，flag 默认关）。V0.3 仅前者落地。
"""
from __future__ import annotations

import os

from .base import BasePublisher, PublishResult
from .mock_browser import MockBrowserPublisher


def get_publisher(name: str) -> BasePublisher:
    if name == "mock_browser":
        # PUBLISH_HEADLESS=0 → 有头模式（路演现场让观众看到浏览器被驱动）
        return MockBrowserPublisher(headless=os.environ.get("PUBLISH_HEADLESS", "1") != "0")
    if name in ("extension_assist", "computer_use"):
        raise ValueError(f"执行器 {name} 为接口占位（PRD v0.3 未启用）")
    raise ValueError(f"未知执行器: {name}")


__all__ = ["BasePublisher", "PublishResult", "MockBrowserPublisher", "get_publisher"]
