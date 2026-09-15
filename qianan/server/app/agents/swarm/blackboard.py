"""多 Agent 共享黑板 + 动作规格（ActionSpec）。

设计原则 —— **模型负责选择下一步，代码负责判定这一步是否允许执行。**

主控（Supervisor）只做一件事：看黑板当前状态，从动作表里挑一个**当前可执行**的动作。
执行 agent（Worker）只做一件事：干完活，把自己改了什么写回黑板。
两者都不自己判断"能不能做"，那是 `ActionSpec.preconditions` 的事。

与旧实现的关键差异：审核失效不再靠一个 `set` 手工维护，而是用**版本号**——
`copy_version` 与 `review_version` 一旦不等，审核结论自动作废。
这样"改过文案却仍宣称已审核"在结构上就不可能发生。
"""
from __future__ import annotations

import time
import uuid
from dataclasses import dataclass, field
from typing import Any

# ---------------------------------------------------------------- 平台状态


@dataclass
class PlatformState:
    """单个平台在黑板上的状态。"""

    platform: str
    display_name: str = ""
    stage: str = "pending"  # pending/copy/reviewed/images/video/failed/skipped
    copy_version: int = 0        # 文案每次改动 +1
    review_version: int = -1     # 最近一次审核时所基于的文案版本（-1 = 从未审核）
    image_version: int = 0
    video_version: int = 0
    issues: list[dict] = field(default_factory=list)
    error: str = ""
    skipped: bool = False
    skip_reason: str = ""

    @property
    def has_copy(self) -> bool:
        return self.copy_version > 0

    @property
    def review_valid(self) -> bool:
        """审核结论是否仍代表当前产物。

        版本号不等 → 审核后文案又被改过 → 结论作废，必须重新审核。
        """
        return self.has_copy and self.review_version == self.copy_version

    @property
    def blocking_issues(self) -> list[dict]:
        return [i for i in self.issues if i.get("severity") == "error"]

    def to_dict(self) -> dict:
        return {
            "platform": self.platform,
            "display_name": self.display_name,
            "stage": self.stage,
            "copy_version": self.copy_version,
            "review_version": self.review_version,
            "has_copy": self.has_copy,
            "review_valid": self.review_valid,
            "blocking": len(self.blocking_issues),
            "error": self.error,
            "skipped": self.skipped,
        }


# ---------------------------------------------------------------- 黑板


class Blackboard:
    """多 Agent 共享的持久化状态。

    主控与各 worker 都只通过它交换信息，彼此不共享推理过程——
    这正是「独立 reviewer 不看到 writer 推理」的结构保证。
    """

    def __init__(self, platforms: list[str], goal: str = "full_package") -> None:
        self.project_id: str = uuid.uuid4().hex[:12]
        self.run_id: str = uuid.uuid4().hex[:8]
        self.goal: str = goal
        self.missing: list[str] = []
        self.understanding: Any = None
        self.understanding_version: int = 0
        self.platforms: dict[str, PlatformState] = {
            p: PlatformState(platform=p) for p in platforms
        }
        self.rules: dict[str, dict] = {}
        self.open_issues: list[str] = []
        self.action_history: list[dict] = []
        self.status: str = "running"  # running/waiting_user/waiting_approval/partial/completed/cancelled
        self.last_error: str = ""
        self.started_at: float = time.monotonic()
        self.budget: dict[str, float] = {
            "max_seconds": 300.0,
            "max_actions": 40,
            "spent_actions": 0,
        }

    # ---- 前置条件检查：动作表靠它决定「现在能不能做」 ----

    def satisfied(self, cond: str) -> bool:
        """判断一条前置条件字符串是否成立。

        支持：`understanding.ready`、`rules.{platform}.ready`、`copy.{platform}.ready`、
              `review.{platform}.valid`、`all.copy.ready`、`all.review.valid`、`always`
        """
        if cond == "always":
            return True
        if cond == "understanding.ready":
            return self.understanding is not None
        if cond == "all.copy.ready":
            return all(s.has_copy or s.skipped for s in self.platforms.values())
        if cond == "all.review.valid":
            return all(s.review_valid or s.skipped for s in self.platforms.values())
        if cond == "no.blocking":
            return not any(s.blocking_issues for s in self.platforms.values())

        for prefix, key in (
            ("rules.", "rules"),
            ("copy.", "copy"),
            ("review.", "review"),
            ("images.", "images"),
        ):
            if cond.startswith(prefix):
                rest = cond[len(prefix):]
                platform, _, tail = rest.partition(".")
                st = self.platforms.get(platform)
                if st is None:
                    return False
                if key == "rules":
                    # 用 in 而非 bool()：规则可能是合法空 dict（该类目无额外约束），
                    # 但"已载入"和"没载入"必须区分开。
                    return platform in self.rules
                if key == "copy":
                    return st.has_copy
                if key == "review":
                    return st.review_valid
                if key == "images":
                    return st.image_version > 0
                _ = tail
        return False

    # ---- 写入：所有状态变更都要经过这里，顺带维护版本与失效关系 ----

    def mark_understanding(self, understanding: Any) -> None:
        self.understanding = understanding
        self.understanding_version += 1

    def mark_copy(self, platform: str, *, display_name: str = "") -> None:
        """文案（重新）生成：版本 +1，此前的所有审核结论自动作废。"""
        st = self.platforms[platform]
        st.copy_version += 1
        if display_name:
            st.display_name = display_name
        st.stage = "copy"

    def mark_reviewed(self, platform: str, issues: list[dict]) -> None:
        st = self.platforms[platform]
        st.issues = issues
        st.review_version = st.copy_version  # 记下审核时所基于的版本
        st.stage = "reviewed" if not st.blocking_issues else "copy"

    def mark_images(self, platform: str) -> None:
        st = self.platforms[platform]
        st.image_version += 1
        st.stage = "images"

    def mark_video(self, platform: str) -> None:
        st = self.platforms[platform]
        st.video_version += 1
        st.stage = "video"

    def mark_failed(self, platform: str, error: str) -> None:
        st = self.platforms[platform]
        st.error = error
        st.stage = "failed"
        self.open_issues.append(f"{platform}: {error}")

    def skip(self, platform: str, reason: str) -> None:
        st = self.platforms[platform]
        st.skipped = True
        st.skip_reason = reason
        st.stage = "skipped"

    def log_action(self, name: str, actor: str, ok: bool, note: str = "") -> None:
        self.action_history.append(
            {
                "seq": len(self.action_history) + 1,
                "action": name,
                "actor": actor,
                "ok": ok,
                "note": note[:160],
                "t": round(time.monotonic() - self.started_at, 2),
            }
        )
        self.budget["spent_actions"] = float(len(self.action_history))

    # ---- 观察：给主控看的状态摘要（不含 worker 的推理过程）----

    def observe(self) -> dict:
        """主控决策时看到的全部信息。刻意不包含任何 worker 的中间推理。"""
        return {
            "goal": self.goal,
            "status": self.status,
            "understanding_ready": self.understanding is not None,
            "platforms": [s.to_dict() for s in self.platforms.values()],
            "open_issues": self.open_issues[-5:],
            "actions_done": len(self.action_history),
            "last_actions": self.action_history[-3:],
            "elapsed": round(time.monotonic() - self.started_at, 1),
        }

    def snapshot(self) -> dict:
        """落盘/回传用的完整快照。"""
        return {
            "project_id": self.project_id,
            "run_id": self.run_id,
            "goal": self.goal,
            "status": self.status,
            "platforms": {k: v.to_dict() for k, v in self.platforms.items()},
            "action_history": self.action_history,
            "open_issues": self.open_issues,
            "budget": self.budget,
            "last_error": self.last_error,
        }


# ---------------------------------------------------------------- 动作规格


@dataclass
class ActionSpec:
    """动作规格：代码判定「这一步是否允许执行」的依据。

    与旧 `ToolSpec` 的差别：旧表只有 name / parameters / handler，
    模型既不知道能不能做，也不知道代价，于是只能靠提示词祈祷。
    """

    name: str
    description: str
    preconditions: list[str] = field(default_factory=list)
    writes: list[str] = field(default_factory=list)
    invalidates: list[str] = field(default_factory=list)
    cost: str = "low"          # low / medium / high
    approval: str = "none"     # none / required
    idempotency_key: str = ""
    isolated: bool = False     # 是否需要在独立上下文里执行（reviewer 必须是）

    def available(self, bb: Blackboard) -> bool:
        return all(bb.satisfied(c) for c in self.preconditions)

    def blocked_by(self, bb: Blackboard) -> list[str]:
        return [c for c in self.preconditions if not bb.satisfied(c)]
