"""千岸 DSH Skills 包 — 提示词加载工具。"""
from __future__ import annotations

import logging
from pathlib import Path

logger = logging.getLogger(__name__)

_PROMPTS_DIR = Path(__file__).resolve().parent.parent / "prompts"
_CACHE: dict[str, str] = {}


def load(name: str) -> str:
    """从 prompts/ 目录加载提示词文件（带 LRU 缓存）。"""
    if name in _CACHE:
        return _CACHE[name]
    path = _PROMPTS_DIR / f"{name}.md"
    if not path.is_file():
        logger.warning("提示词文件不存在: %s", path)
        return ""
    text = path.read_text(encoding="utf-8")
    _CACHE[name] = text
    return text


def clear_cache() -> None:
    """提示词热更新后调用：清除缓存使新文件生效。"""
    _CACHE.clear()
