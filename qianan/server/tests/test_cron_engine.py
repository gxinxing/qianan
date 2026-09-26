"""CronEngine 定时自动化引擎测试。"""
from __future__ import annotations

import asyncio

from app.cron_engine import cron_engine


def test_cron_trigger_once(monkeypatch):
    """cron 集成测试不触网（conftest 约定）：强制确定性 Mock 客户端。

    历史包袱：本测试曾依赖「百炼欠费 → 快速降级 Mock」侥幸不触网，
    在本地网关可达（如 Codely）时会真实调用烧积分且拖慢全套 189s。
    """
    monkeypatch.setenv("QIANAN_MOCK", "1")
    res = asyncio.run(cron_engine.trigger_once())
    assert res["status"] == "completed"
    assert "task_id" in res
    assert res["lessons_distilled"] >= 0
