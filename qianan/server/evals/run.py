"""Evals runner：跑全部快照用例，输出 JSON 报告并打印摘要。

用法：cd server && /usr/bin/python3 -m evals.run
报告：server/data/evals/report.json（B 模块前端 /agent 页消费）
"""
from __future__ import annotations

import json
import time
from pathlib import Path

from .cases import SUITES, Case, Suite

REPORT_DIR = Path(__file__).resolve().parents[1] / "data" / "evals"
REPORT_PATH = REPORT_DIR / "report.json"


def _run_case(case: Case) -> dict:
    rec = {
        "id": case.id,
        "name": case.name,
        "passed": False,
        "skipped": False,
        "expect": case.expect,
        "got": "",
        "note": "",
    }
    try:
        ok, got, skipped, note = case.fn()
        rec["passed"] = bool(ok)
        rec["skipped"] = bool(skipped)
        rec["got"] = got
        rec["note"] = note or ""
    except Exception as exc:  # noqa: BLE001 —— 单用例异常不炸整个 runner
        rec["passed"] = False
        rec["got"] = "用例执行异常"
        rec["note"] = f"{type(exc).__name__}: {exc}"
    return rec


def run_all() -> dict:
    t0 = time.time()
    suites_out = []
    total = passed = failed = skipped = 0
    for suite in SUITES:
        cases_out = [_run_case(c) for c in suite.cases]
        suites_out.append({"name": suite.name, "desc": suite.desc, "cases": cases_out})
        total += len(cases_out)
        passed += sum(1 for c in cases_out if c["passed"] and not c["skipped"])
        skipped += sum(1 for c in cases_out if c["skipped"])
    failed = total - passed - skipped
    report = {
        "generated_at": time.time(),
        "total": total,
        "passed": passed,
        "failed": failed,
        "skipped": skipped,
        "duration_ms": round((time.time() - t0) * 1000, 1),
        "suites": suites_out,
    }
    REPORT_DIR.mkdir(parents=True, exist_ok=True)
    REPORT_PATH.write_text(
        json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    return report


def _print_summary(report: dict) -> None:
    print(
        f"Evals 摘要：总 {report['total']} ｜ passed {report['passed']} ｜ "
        f"failed {report['failed']} ｜ skipped {report['skipped']} ｜ "
        f"{report['duration_ms']}ms"
    )
    for suite in report["suites"]:
        cases = suite["cases"]
        p = sum(1 for c in cases if c["passed"])
        s = sum(1 for c in cases if c["skipped"])
        print(f"  [{suite['name']}] {p}/{len(cases)} passed" + (f"（{s} skipped）" if s else ""))
        for c in cases:
            if not c["passed"] and not c["skipped"]:
                print(f"    ✗ {c['id']}  expect: {c['expect']}")
                print(f"      got: {c['got']}")
                if c["note"]:
                    print(f"      note: {c['note']}")
    print(f"报告已写入：{REPORT_PATH}")


def main() -> None:
    report = run_all()
    _print_summary(report)


if __name__ == "__main__":
    main()
