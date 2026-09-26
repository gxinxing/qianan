"""CronEngine 定时自动化引擎测试。"""
from __future__ import annotations

import asyncio
import pytest

from app.cron_engine import cron_engine


def test_cron_trigger_once():
    res = asyncio.run(cron_engine.trigger_once())
    assert res["status"] == "completed"
    assert "task_id" in res
    assert res["lessons_distilled"] >= 0
