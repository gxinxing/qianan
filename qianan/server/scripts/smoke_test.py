#!/usr/bin/env python3
"""千岸后端 Smoke Test：验证 API + Agent 流水线基本可用。

用法：
  cd qianan/server && python3 scripts/smoke_test.py               # Mock 模式（默认）
  QIANAN_MOCK=0 BAILIAN_API_KEY=<key> python3 scripts/smoke_test.py  # 真实百炼 API

退出码：
  0 — 全部通过
  1 — 有必选项失败
  2 — 环境/依赖缺失
"""
from __future__ import annotations

import asyncio
import os
import sys
import time
from pathlib import Path
from typing import Any


# =====================================================================
# 环境设置 — ★ 必须在 import app 之前执行（被 .env 覆盖的风险）
# =====================================================================

def _setup_mock_env() -> None:
    """强制 Mock 模式：不管 .env 里写什么，Smoke Test 走确定性 mock。"""
    os.environ["QIANAN_MOCK"] = "1"
    if not os.environ.get("BAILIAN_API_KEY"):
        os.environ["BAILIAN_API_KEY"] = "smoke-test-mock-key"


def _check_env() -> bool:
    """确保 server 目录在 sys.path 且依赖可 import。"""
    server_dir = Path(__file__).resolve().parents[2] / "server"
    if str(server_dir) not in sys.path:
        sys.path.insert(0, str(server_dir))
    ok = True
    missing = []
    for mod in ("fastapi", "pydantic", "requests", "PIL"):
        try:
            __import__(mod)
        except ImportError:
            missing.append(mod)
    if missing:
        print(f"✗ 缺少依赖: {', '.join(missing)}")
        print(f"  运行: pip install {' '.join(missing)}")
        ok = False
    return ok


# =====================================================================
# 测试用例
# =====================================================================

class TestCase:
    def __init__(self, name: str, required: bool = True):
        self.name = name
        self.required = required
        self.passed = False
        self.skipped = False
        self.blocked = False
        self.detail = ""

    def ok(self, detail: str = "") -> None:
        self.passed = True
        self.detail = detail

    def skip(self, reason: str) -> None:
        self.skipped = True
        self.detail = reason

    def block(self, reason: str) -> None:
        self.blocked = True
        self.detail = reason

    def fail(self, detail: str) -> None:
        self.detail = detail


async def run_tests() -> int:
    # ★ 在 import app 之前确保 mock 环境就位
    _setup_mock_env()

    from fastapi.testclient import TestClient  # noqa: E402
    from app.main import app  # noqa: E402
    from app.economics import EconomicsInput  # noqa: E402

    # with 语句触发 lifespan → _client = get_client() 被初始化
    with TestClient(app) as client:
        results: list[TestCase] = []

    # ---- 1. Health Check ----
    t = TestCase("Health Check (GET /api/health)", required=True)
    results.append(t)
    try:
        r = client.get("/api/health")
        if r.status_code == 200:
            data = r.json()
            t.ok(f"status=ok  mock={data.get('mock')}")
        else:
            t.fail(f"HTTP {r.status_code}: {r.text[:120]}")
    except Exception as e:
        t.fail(str(e))

    # ---- 2. Rules Load ----
    t = TestCase("Rules Load (GET /api/rules)", required=True)
    results.append(t)
    try:
        r = client.get("/api/rules")
        if r.status_code == 200:
            data = r.json()
            count = len(data) if isinstance(data, dict) else 0
            platforms = list(data.keys()) if isinstance(data, dict) else []
            t.ok(f"{count} platforms loaded: {', '.join(platforms)}")
        else:
            t.fail(f"HTTP {r.status_code}: {r.text[:200]}")
    except FileNotFoundError as e:
        t.block(f"规则目录不存在: {e} — 需创建 server/rules/*.json")
    except Exception as e:
        t.fail(str(e))

    # ---- 3. Ideation ----
    t = TestCase("Ideation (POST /api/ideation)", required=True)
    results.append(t)
    try:
        r = client.post("/api/ideation", json={"market": "us", "category": "home_kitchen"})
        if r.status_code == 200:
            data = r.json()
            ideas = data.get("suggestions", [])
            t.ok(f"{len(ideas)} suggestions  source={data.get('trend_source', '?')}")
        else:
            t.fail(f"HTTP {r.status_code}: {r.text[:200]}")
    except Exception as e:
        t.fail(str(e))

    # ---- 4. Economics ----
    t = TestCase("Economics (POST /api/economics)", required=True)
    results.append(t)
    try:
        payload = EconomicsInput(
            cost_cny=12, weight_kg=0.3, length_cm=20, width_cm=15, height_cm=8,
            target_margin=0.15, first_mile="sea", turnover_months=2, fixed_cost_cny=3000,
        ).model_dump()
        r = client.post("/api/economics", json=payload)
        if r.status_code == 200:
            eco = r.json()
            n = len(eco.get("platforms", []))
            t.ok(f"{n} platforms  fx={eco.get('fx_usd_cny', '?')}  source={eco.get('fx_source', '?')}")
        else:
            t.fail(f"HTTP {r.status_code}: {r.text[:200]}")
    except Exception as e:
        t.fail(str(e))

    # ---- 5. Audit ----
    t = TestCase("Audit Draft (POST /api/audit)", required=True)
    results.append(t)
    try:
        r = client.post("/api/audit", json={
            "platform": "amazon", "category": "home_kitchen",
            "title": "Portable Blender 380ml USB-C Fast Charge Stepless Speed",
            "bullets": ["10s blending", "Detachable cup", "Only 380g", "#1 Best Seller"],
            "description": "A portable blender with USB-C fast charge and stepless speed control.",
            "attributes": {"brand": "QB", "model": "380ml-B", "power": "200W"},
            "images": ["https://example.com/img.png"],
        })
        if r.status_code == 200:
            data = r.json()
            issues = data.get("issues", [])
            errors = [i for i in issues if i.get("severity") == "error"]
            warns = [i for i in issues if i.get("severity") == "warn"]
            t.ok(f"passed={data.get('passed')}  errors={len(errors)}  warns={len(warns)}")
        else:
            t.fail(f"HTTP {r.status_code}: {r.text[:200]}")
    except FileNotFoundError as e:
        t.block(f"规则目录不存在: {e}")
    except Exception as e:
        t.fail(str(e))

    # ---- 6. Skills Registry ----
    t = TestCase("Skills Registry (GET /api/skills/registry)", required=False)
    results.append(t)
    try:
        r = client.get("/api/skills/registry")
        if r.status_code == 200:
            data = r.json()
            skills = data.get("registry", [])
            installed = [s for s in skills if s.get("installed")]
            t.ok(f"{len(skills)} total, {len(installed)} installed")
        else:
            t.fail(f"HTTP {r.status_code}: {r.text[:120]}")
    except Exception as e:
        t.fail(str(e))

    # ---- 7. Generate Pipeline (Mock 模式, 30s 超时) ----
    t = TestCase("Generate Pipeline (POST /api/generate)", required=True)
    results.append(t)
    try:
        r = client.post("/api/generate", json={
            "product_name": "Portable Blender 380ml",
            "selling_points": "USB-C fast charge, 10s blending, detachable cup, 380g",
            "category": "home_kitchen",
            "platforms": ["amazon", "shopee"],
        })
        if r.status_code != 200:
            t.fail(f"HTTP {r.status_code}: {r.text[:200]}")
        else:
            task_id = r.json().get("task_id", "")
            if not task_id:
                t.fail("response missing task_id")
            else:
                # Mock 模式下 pipeline 应该 15s 内完成
                max_polls = 30
                for i in range(max_polls):
                    await asyncio.sleep(1)
                    pr = client.get(f"/api/tasks/{task_id}")
                    if pr.status_code != 200:
                        continue
                    pd = pr.json()
                    status_val = pd.get("status", "")
                    if status_val in ("done", "failed"):
                        elapsed = i + 1
                        if status_val == "done":
                            listings = pd.get("listings", []) or []
                            parts = [
                                f"{l.get('platform','?')}={'✓' if l.get('compliance_passed') else '✗'}"
                                for l in listings
                            ]
                            t.ok(f"done in {elapsed}s  [{', '.join(parts)}]")
                        else:
                            err = pd.get("error", "unknown")
                            t.fail(f"failed after {elapsed}s: {err[:120]}")
                        break
                else:
                    t.fail(f"timeout after {max_polls}s, status=running")
    except FileNotFoundError as e:
        t.block(f"规则目录不存在: {e}")
    except Exception as e:
        t.fail(str(e))

    # ---- 8. Admin Stats ----
    t = TestCase("Admin Stats (GET /api/admin/stats)", required=False)
    results.append(t)
    try:
        r = client.get("/api/admin/stats")
        if r.status_code == 200:
            data = r.json()
            t.ok(f"tasks={data.get('tasks', {}).get('total', '?')}")
        else:
            t.fail(f"HTTP {r.status_code}: {r.text[:120]}")
    except Exception as e:
        t.fail(str(e))

    # ---- 9. Feedback ----
    t = TestCase("Feedback (POST /api/feedback)", required=False)
    results.append(t)
    try:
        r = client.post("/api/feedback", json={
            "task_id": "smoke-test", "platform": "amazon", "rating": 1, "comment": "smoke"
        })
        if r.status_code == 200:
            t.ok("feedback accepted")
        else:
            t.fail(f"HTTP {r.status_code}: {r.text[:120]}")
    except Exception as e:
        t.fail(str(e))

    # ---- 10. Files List ----
    t = TestCase("Files List (GET /api/files)", required=False)
    results.append(t)
    try:
        r = client.get("/api/files")
        if r.status_code == 200:
            data = r.json()
            pkgs = data.get("packages", [])
            t.ok(f"{len(pkgs)} packages on disk")
        else:
            t.fail(f"HTTP {r.status_code}: {r.text[:120]}")
    except Exception as e:
        t.fail(str(e))

    # ---- 11. Trends ----
    t = TestCase("Trends (GET /api/trends)", required=False)
    results.append(t)
    try:
        r = client.get("/api/trends?market=us")
        if r.status_code == 200:
            data = r.json()
            t.ok(f"trend_source={data.get('trend_source', '?')}")
        else:
            t.fail(f"HTTP {r.status_code}")
    except Exception as e:
        t.fail(str(e))

    # =================================================================
    # 输出报告
    # =================================================================
    print("\n" + "=" * 60)
    print("千岸后端 Smoke Test 结果")
    print("=" * 60)

    passed = 0
    failed = 0
    skipped = 0
    blocked = 0
    failed_required = []

    for t in results:
        if t.blocked:
            blocked += 1
            print(f"  🔴  被阻塞   {t.name}")
            print(f"         原因: {t.detail}")
        elif t.skipped:
            skipped += 1
            print(f"  SKIP  {t.name} — {t.detail}")
        elif t.passed:
            passed += 1
            detail = f"  ✓  {t.name}" + (f"  {t.detail}" if t.detail else "")
            print(detail)
        else:
            failed += 1
            tag = "✗" if t.required else "⚠"
            print(f"  {tag}   {t.name}  → {t.detail}")
            if t.required:
                failed_required.append(t.name)

    print("-" * 60)
    print(f"  总计: {len(results)}  |  ✓ {passed}  |  ✗ {failed}  |  SKIP {skipped}  |  🔴 {blocked}")

    if failed_required:
        print(f"\n  FAILED (required): {', '.join(failed_required)}")
    if blocked:
        print(f"\n  BLOCKED: {blocked} 个测试因环境/依赖问题无法执行")

    print("=" * 60)

    if failed_required:
        print("\n❌ Smoke test FAILED — 必选项未通过")
        return 1
    elif blocked:
        if passed >= len(results) - blocked - failed:
            print("\n⚠  Smoke test PARTIAL — 有阻塞项但可选项均通过")
            return 0
        return 1
    elif failed > 0:
        print("\n⚠  Smoke test PARTIAL — 可选项有失败")
        return 0
    else:
        print("\n✅ All smoke tests PASSED")
        return 0


def main() -> int:
    # ★ Mock 模式必须在任何 app 模块 import 之前设置
    _setup_mock_env()

    if not _check_env():
        return 2
    try:
        return asyncio.run(run_tests())
    except Exception as e:
        print(f"\n✗ 未预期的异常: {e}")
        import traceback
        traceback.print_exc()
        return 2


if __name__ == "__main__":
    sys.exit(main())
