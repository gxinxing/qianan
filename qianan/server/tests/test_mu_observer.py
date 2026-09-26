"""MuObserver 独立观察者 Agent 测试套件。"""
from __future__ import annotations

from app.agents.mu_observer import mu_observer
from app.schemas import ComplianceIssue, PlatformListing


def test_mu_observer_normal_pass():
    snapshot = {"status": "completed", "actions": [{"action": "generate_copy"}, {"action": "review_listing"}]}
    listings = [PlatformListing(platform="amazon", title="Sample Title")]
    report = mu_observer.observe_swarm(snapshot, listings)
    assert report.verdict == "PASS"
    assert report.quality_score == 1.0


def test_mu_observer_detects_unfixed_errors():
    snapshot = {"status": "running", "actions": [{"action": "generate_copy"}]}
    listings = [
        PlatformListing(
            platform="amazon",
            title="Sample Title",
            compliance=[ComplianceIssue(check_id="c1", severity="error", field="title", message="Overlength")],
        )
    ]
    report = mu_observer.observe_swarm(snapshot, listings)
    assert len(report.anomalies_detected) > 0
    assert report.quality_score < 1.0
