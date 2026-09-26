"""独立观摩与检测 Agent (MuObserver / MuInspector)。

参考 mu (qybaihe/mu) 的独立裁判与观察者哲学：
- 站在外部第三方角度无偏见地观察千岸蜂群 Worker 的动作与产物；
- 避免与千岸内部 Worker 共享 Prompt 推理链，确保审核的真实性；
- 输出纯粹的观测日志、评分与判定报告，指导系统的持续优化。
"""
from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from typing import Any

from ..schemas import PlatformListing

logger = logging.getLogger(__name__)


@dataclass
class ObservationReport:
    """Mu 观察者产出的结构化评价报告。"""
    timestamp: float = field(default_factory=time.time)
    swarm_status: str = "running"
    total_actions: int = 0
    anomalies_detected: list[str] = field(default_factory=list)
    quality_score: float = 1.0
    verdict: str = "PASS"
    summary: str = ""


class MuObserver:
    """独立外部观察 Agent (Mu Inspector)。"""

    def observe_swarm(self, blackboard_snapshot: dict[str, Any], listings: list[PlatformListing]) -> ObservationReport:
        """无偏见审查千岸蜂群当前的运行动向与产物表现。"""
        actions = blackboard_snapshot.get("actions", [])
        status = blackboard_snapshot.get("status", "running")
        
        anomalies = []
        # 1. 检查是否有重复无效的动作推演
        action_names = [a.get("action") for a in actions if isinstance(a, dict)]
        if len(action_names) > 10 and len(set(action_names)) < 3:
            anomalies.append("蜂群陷入低效死循环推演")

        # 2. 检查产物是否存在未修补的严重合规漏洞
        unfixed_errors = 0
        for listing in listings:
            if listing.compliance:
                unfixed_errors += sum(1 for i in listing.compliance if i.severity == "error")

        if unfixed_errors > 0:
            anomalies.append(f"检测到 {unfixed_errors} 处未解决的阻断级合规硬伤")

        score = max(0.0, 1.0 - len(anomalies) * 0.3)
        verdict = "PASS" if score >= 0.7 else "WARN" if score >= 0.4 else "FAIL"

        return ObservationReport(
            swarm_status=status,
            total_actions=len(actions),
            anomalies_detected=anomalies,
            quality_score=round(score, 2),
            verdict=verdict,
            summary=f"Mu 观察完成: 得分 {score:.2f}, 结论={verdict}, 异常数={len(anomalies)}",
        )


mu_observer = MuObserver()
