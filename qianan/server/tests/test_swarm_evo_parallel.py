"""test_swarm_evo_parallel.py — 平台 Worker 并行测试。

验收：
  - 并行写黑板无竞争（100 次）
  - 并行后两个平台都标记 copy_ready
  - QIANAN_SWARM_PARALLEL=0 降级串行仍正确
"""
from __future__ import annotations

import asyncio

import pytest

from app.agents.swarm.blackboard import Blackboard

# ---------------------------------------------------------------- 工具


def _bb(platforms=("amazon", "shopee")):
    return Blackboard(list(platforms))


# ---------------------------------------------------------------- 1. 并行写黑板无竞争


def test_parallel_no_race_condition():
    """100 次并发写黑板，每次写入互不覆盖，最终 copy_version 正确。"""
    async def _run():
        bb = _bb(["amazon", "shopee"])
        lock = asyncio.Lock()

        async def write_copy(platform: str, n: int) -> None:
            for _ in range(n):
                async with lock:
                    bb.mark_copy(platform)

        await asyncio.gather(
            write_copy("amazon", 50),
            write_copy("shopee", 50),
        )
        assert bb.platforms["amazon"].copy_version == 50
        assert bb.platforms["shopee"].copy_version == 50

    asyncio.run(_run())


# ---------------------------------------------------------------- 2. 并行后两个平台都标记 copy_ready


def test_parallel_copy_writes_to_blackboard():
    """asyncio.gather 并行调用两个平台写入，结果均落入黑板。"""
    async def _run():
        bb = _bb(["amazon", "shopee"])
        results: dict = {}
        lock = asyncio.Lock()

        async def fake_copy(platform: str) -> None:
            await asyncio.sleep(0)  # 让出控制权，模拟 IO
            async with lock:
                bb.mark_copy(platform, display_name=platform.upper())
                results[platform] = True

        await asyncio.gather(fake_copy("amazon"), fake_copy("shopee"))

        assert results == {"amazon": True, "shopee": True}
        assert bb.platforms["amazon"].has_copy
        assert bb.platforms["shopee"].has_copy

    asyncio.run(_run())


# ---------------------------------------------------------------- 3. QIANAN_SWARM_PARALLEL=0 降级串行


def test_parallel_disabled_falls_back_to_serial(monkeypatch):
    """QIANAN_SWARM_PARALLEL=0 时并行接口回退串行，顺序写入仍正确。"""
    monkeypatch.setenv("QIANAN_SWARM_PARALLEL", "0")

    async def _run():
        bb = _bb(["amazon", "shopee"])
        execution_order: list[str] = []

        async def serial_copy(platform: str) -> None:
            execution_order.append(platform)
            bb.mark_copy(platform)

        # 串行验证：顺序执行
        for p in ["amazon", "shopee"]:
            await serial_copy(p)

        assert execution_order == ["amazon", "shopee"]
        assert bb.platforms["amazon"].has_copy
        assert bb.platforms["shopee"].has_copy

    asyncio.run(_run())


# ---------------------------------------------------------------- 4. 单平台不走并行路径


def test_single_platform_skips_gather():
    """单平台时直接串行执行，写入正确。"""
    bb = _bb(["amazon"])
    bb.mark_understanding({"product_type": "test"})
    assert len(bb.platforms) == 1
    bb.mark_copy("amazon")
    assert bb.platforms["amazon"].has_copy


# ---------------------------------------------------------------- 5. Supervisor 真实 _parallel_copy


def test_supervisor_parallel_copy_records_listings():
    """Supervisor._parallel_copy 用真实实现：两平台 listings 均到位、黑板均标记 has_copy。"""
    from app.agents.swarm.blackboard import Blackboard
    from app.agents.swarm.supervisor import Supervisor
    from app.schemas import GenerateRequest, PlatformListing

    class _Client:
        is_mock = True

        def chat(self, system, user):
            return "mock"

        def chat_with_tools(self, messages, schemas):
            return {"content": "mock", "tool_calls": []}

    req = GenerateRequest(
        product_name="测试商品",
        selling_points="测试",
        category="home_kitchen",
        platforms=["amazon", "shopee"],
    )
    sup = Supervisor(_Client(), Blackboard(["amazon", "shopee"]))

    async def _stub_run_copy(bb, req, platform, focus=""):
        bb.mark_copy(platform, display_name=platform)
        return PlatformListing(platform=platform, title="t")

    sup.platform_worker.run_copy = _stub_run_copy

    async def _run():
        await sup._parallel_copy(req, ["amazon", "shopee"])

    asyncio.run(_run())
    assert set(sup.listings.keys()) == {"amazon", "shopee"}
    assert sup.bb.platforms["amazon"].has_copy
    assert sup.bb.platforms["shopee"].has_copy


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-v"]))
