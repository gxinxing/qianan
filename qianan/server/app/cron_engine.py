"""定时自动化上新与自进化 Cron 引擎 (CronEngine)。

功能：
1. 后台无人值守后台自动化轮询（模拟全天候实时选品/巡检上新）
2. 自动触发 Swarm 蜂群并发调度（理解 -> 选词 -> 防御防封 -> 生成图片/视频 -> 审核）
3. 自动化结束后由 Evolution Agent 提取教训，回写 MemoryStore 与平台 Patch
"""
from __future__ import annotations

import asyncio
import logging
import time
from typing import Any

from .agents.evolution import EvolutionAgent
from .agents.swarm import run_swarm
from .bailian.client import get_client
from .judge import JudgmentKernel
from .schemas import GenerateRequest, TaskRecord
from .task_store import create_task

logger = logging.getLogger(__name__)

# 模拟定时自动上新的热销选品库
AUTOMATED_PRODUCTS = [
    {
        "name": "智能声波电动牙刷",
        "selling_points": "42000次/分高频振动，IPX7防水，Type-C快充，无铜杜邦软毛",
        "category": "home_kitchen",
        "platforms": ["amazon", "shopee", "tiktokshop"],
    },
    {
        "name": "户外便携折叠露营椅",
        "selling_points": "航空级铝合金支架，150kg超强承重，双侧收纳网袋，3秒快速收纳",
        "category": "sports_outdoors",
        "platforms": ["amazon", "shopee", "lazada"],
    },
    {
        "name": "磁吸无线充移动电源",
        "selling_points": "10000mAh强力磁吸，15W无线快充，自带隐藏式支架，小巧轻薄不卡镜头",
        "category": "electronics",
        "platforms": ["amazon", "shopee", "aliexpress", "tiktokshop"],
    },
]


class AutonomousCronEngine:
    """无人值守定时自动化 Agent 引擎。"""

    def __init__(self) -> None:
        self.is_running = False
        self._counter = 0

    async def trigger_once(self) -> dict[str, Any]:
        """主动触发一次自动化蜂群上新与自进化闭环。"""
        prod = AUTOMATED_PRODUCTS[self._counter % len(AUTOMATED_PRODUCTS)]
        self._counter += 1

        req = GenerateRequest(
            product_name=prod["name"],
            selling_points=prod["selling_points"],
            category=prod["category"],
            platforms=prod["platforms"],
        )

        # 1. 判定核 preflight 校验
        verdict = JudgmentKernel().judge_input_preflight(req)
        if not verdict.allowed:
            logger.warning("Cron 判定核拦截: %s", verdict.reason)
            return {"status": "rejected", "reason": verdict.reason}

        task = create_task(req)
        client = get_client()

        logger.info("🤖 CronEngine 自动触发蜂群上新任务: id=%s product=%s", task.task_id, req.product_name)

        # 2. 运行 Swarm 蜂群调度
        result = await run_swarm(task, client, req)

        # 3. 进化 Agent 自动经验蒸馏与规则 Patch 回写
        evo_agent = EvolutionAgent(client)
        lessons = evo_agent.distill_experience(req, task.listings)

        return {
            "status": "completed",
            "task_id": task.task_id,
            "product": req.product_name,
            "platforms": req.platforms,
            "swarm_result": result.get("status"),
            "lessons_distilled": len(lessons),
            "timestamp": time.time(),
        }

    async def start_loop(self, interval_seconds: int = 180) -> None:
        """开启后台定时轮询循环。"""
        self.is_running = True
        logger.info("🚀 AutonomousCronEngine 启动后台自动轮询，间隔: %ds", interval_seconds)
        while self.is_running:
            try:
                await self.trigger_once()
            except Exception as exc:  # noqa: BLE001
                logger.exception("Cron 循环跑偏异常: %s", exc)
            await asyncio.sleep(interval_seconds)


cron_engine = AutonomousCronEngine()
