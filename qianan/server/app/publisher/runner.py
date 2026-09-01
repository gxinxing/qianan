"""上架编排：状态机驱动 + 重试（≤2 次，指数退避）+ 全程留痕落盘。"""
from __future__ import annotations

import asyncio
import logging
import time

from ..schemas import PublishStatus
from . import get_publisher, store

logger = logging.getLogger(__name__)

MAX_RETRIES = 2


async def run_publish(job_id: str, listing: dict) -> None:
    """后台执行：queued → running → live | failed（失败按 2s/4s 退避重试）。"""
    job = store.get_job(job_id)
    if job is None:
        logger.warning("PublishJob 不存在: %s", job_id)
        return
    try:
        publisher = get_publisher(job["executor"])
    except ValueError as exc:
        job["status"] = PublishStatus.failed.value
        job["last_error"] = str(exc)
        store.save_job(job)
        return

    for attempt in range(MAX_RETRIES + 1):
        job["status"] = PublishStatus.running.value
        job["attempts"] = attempt + 1
        store.save_job(job)
        result = await publisher.publish(listing, store.job_dir(job_id))
        job["steps"] = (job.get("steps") or []) + [s.model_dump(mode="json") for s in result.steps]
        if result.ok:
            job["status"] = PublishStatus.live.value
            job["live_url"] = result.live_url
            job["listing_id"] = result.listing_id
            job["published_at"] = time.time()
            job["last_error"] = None
            store.save_job(job)
            logger.info("上架成功（job %s → %s）", job_id, result.listing_id)
            return
        job["last_error"] = result.error
        store.save_job(job)
        if attempt < MAX_RETRIES:
            await asyncio.sleep(2 ** (attempt + 1))  # 2s → 4s 指数退避

    job["status"] = PublishStatus.failed.value
    store.save_job(job)
    logger.warning("上架失败（job %s，%d 次尝试）：%s", job_id, job["attempts"], job["last_error"])
