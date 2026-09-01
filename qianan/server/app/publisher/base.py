"""上架执行器基类：统一 publish 契约。

可见性硬约束（PRD v0.3）：每个动作必须写 steps[] 并附截图；
无留痕的静默执行视同黑盒，等同驳回。
"""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from ..schemas import PublishStep


@dataclass
class PublishResult:
    ok: bool
    live_url: str = ""
    listing_id: str = ""
    error: str = ""
    steps: list[PublishStep] = field(default_factory=list)


class BasePublisher:
    """执行器接口：输入上架包快照 + job 目录（截图落点），输出结构化结果。"""

    name = "base"

    async def publish(self, listing: dict, job_dir: Path) -> PublishResult:
        raise NotImplementedError
