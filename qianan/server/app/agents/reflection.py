"""⑥ 评审 Agent · 自我反思：任务完成后对比「商品事实档案 vs 最终输出 + 合规历史」。

真实模式：LLM 逐平台反思，蒸馏可复用教训写入记忆库；文案忠于事实且合规干净时
保持沉默（输出空数组），不往记忆里掺水。
Mock / LLM 失败：回退确定性模板蒸馏（仅自愈成功且终态合规的平台产教训）。
"""
from __future__ import annotations

import asyncio
import json
import logging
import re

from .. import memory_store
from ..agent_core.trace import record
from ..bailian.client import BailianLike
from ..schemas import PlatformListing, TaskRecord, Understanding

logger = logging.getLogger(__name__)

SYSTEM = """你是千岸跨境上架平台的评审 Agent，负责任务完成后的复盘反思。
对比「商品事实档案」（商品理解的结构化输出，视为事实）与「最终上架文案」，找出夸大、失真或无事实依据的表述；结合合规自愈修订历史，蒸馏出可直接指导后续生成的教训。
输出严格 JSON（不要 markdown 代码块、不要多余文字）：{"lessons": ["一条教训，不超过40字，写成『遇到X时应Y』的形式"]}
文案忠于事实且合规干净时输出 {"lessons": []}。不要为了凑数编造教训，最多 2 条。"""


async def self_reflect(task: TaskRecord, client: BailianLike) -> None:
    """评审 Agent 反思入口：逐平台并行；单平台失败只影响该平台。"""
    if not task.listings:
        return
    task.stage = "评审 Agent 反思中"
    if client.is_mock:
        for listing in task.listings:
            _remember_template(task, listing)
        return
    await asyncio.gather(*(_reflect_one(task, client, task.understanding, l) for l in task.listings))


async def _reflect_one(
    task: TaskRecord, client: BailianLike, understanding: Understanding | None, listing: PlatformListing
) -> None:
    platform = listing.platform
    try:
        raw = await asyncio.to_thread(client.chat, SYSTEM, _prompt(understanding, listing))
        parsed = _extract_json(raw).get("lessons")
        lessons = [str(x).strip() for x in (parsed or []) if str(x).strip()][:2]
    except Exception as exc:  # noqa: BLE001
        record(task, "reflect", f"self_reflect[{platform}]", "LLM 反思失败", str(exc)[:80], "fallback")
        _remember_template(task, listing)
        return
    if not lessons:
        record(task, "reflect", f"self_reflect[{platform}]", "复盘", "文案忠于事实且合规干净，无新教训")
        return
    for lesson in lessons:
        memory_store.remember(
            platform=platform,
            category=task.request.category,
            lesson=lesson[:80],
            source_task=task.task_id,
        )
        record(task, "reflect", f"self_reflect[{platform}]", "蒸馏教训", lesson[:60])


def _remember_template(task: TaskRecord, listing: PlatformListing) -> None:
    """确定性模板蒸馏（兜底路径）：只记录「自愈成功」的经验。"""
    if listing.revised_count <= 0 or not listing.compliance_passed:
        record(task, "reflect", f"self_reflect[{listing.platform}]", "复盘", "无需蒸馏（无自愈或终态未合规）")
        return
    lesson = f"{listing.platform}：修订 {listing.revised_count} 轮后合规通过，生成时预留合规余量"
    memory_store.remember(
        platform=listing.platform,
        category=task.request.category,
        lesson=lesson,
        source_task=task.task_id,
    )
    record(task, "reflect", f"self_reflect[{listing.platform}]", "模板蒸馏", lesson[:60])


def _prompt(u: Understanding | None, listing: PlatformListing) -> str:
    if u:
        facts = (
            f"- 商品类型：{u.product_type}\n"
            f"- 材质：{u.material or '未知'}\n"
            f"- 卖点：{'；'.join(u.selling_points[:5])}\n"
            f"- 目标受众：{u.target_audience or '未知'}\n"
            f"- 属性：{json.dumps(u.attributes, ensure_ascii=False)[:200]}"
        )
    else:
        facts = "- （缺失）"
    residual = [i for i in listing.compliance if i.severity == "error"]
    heal = f"{listing.revised_count} 轮修订" if listing.revised_count else "0 轮（一次通过）"
    return f"""商品事实档案（商品理解 Agent 输出，视为事实）：
{facts}

最终上架文案（{listing.display_name or listing.platform} 平台）：
标题：{listing.title[:200]}
五点/要点：{'；'.join(listing.bullets[:2])[:300] or '（无）'}
描述（节选）：{listing.description[:300]}

自愈历史：{heal}；终检遗留问题：{'；'.join(i.message for i in residual[:3]) or '无'}

请对比事实与文案进行反思，输出 JSON。"""


def _extract_json(text: str) -> dict:
    match = re.search(r"\{.*\}", text, re.DOTALL)
    if not match:
        raise ValueError(f"反思输出无法解析: {text[:200]}")
    return json.loads(match.group(0))
