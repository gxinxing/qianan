"""判定核 (Judgment Kernel) 测试套件。"""
from __future__ import annotations

import pytest

from app.judge import JudgmentKernel
from app.schemas import ComplianceIssue, GenerateRequest, PlatformListing


def test_judge_input_preflight_valid():
    jk = JudgmentKernel()
    req = GenerateRequest(product_name="榨汁杯", selling_points="快充", platforms=["amazon"])
    verdict = jk.judge_input_preflight(req)
    assert verdict.allowed is True
    assert verdict.score == 1.0


def test_judge_input_preflight_invalid():
    jk = JudgmentKernel()
    req = GenerateRequest(product_name="", selling_points="", platforms=["amazon"])
    verdict = jk.judge_input_preflight(req)
    assert verdict.allowed is False


def test_judge_tool_risk_detected():
    jk = JudgmentKernel()
    verdict = jk.judge_tool_risk("amazon", "这是行业绝对第一的神药")
    assert verdict.allowed is False
    assert "绝对" in verdict.details["hit_words"]


def test_judge_turn_completion():
    jk = JudgmentKernel()
    listings = {
        "amazon": PlatformListing(
            platform="amazon",
            display_name="Amazon",
            title="Blender",
            bullets=["Fast"],
            description="Desc",
            compliance=[ComplianceIssue(check_id="c1", severity="warn", field="title", message="OK")],
        )
    }
    # 平台全覆盖且审核通过
    verdict = jk.judge_turn_completion(["amazon"], listings, {"amazon"})
    assert verdict.allowed is True
