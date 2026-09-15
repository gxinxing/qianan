"""输入理解②：意图 Agent —— 判定「用户到底要干什么」。

与第一层的分工：
- ① 商品理解（understanding.py）回答「这是什么商品」→ 商品事实
- ② 意图理解（本文件）     回答「用户要干什么」→ 决定本次任务的**动作空间**

设计取舍：
- **只在用户写了诉求文本时才调模型**。没写诉求 = 默认出完整包，零额外延迟与成本；
  这样绝大多数现有请求（前端不填诉求）行为完全不变。
- 判定失败一律回退「出完整上架包」，绝不静默降级到更少的产出 ——
  少给东西比多给东西危险得多（卖家可能没注意到少了主图）。
"""
from __future__ import annotations

import asyncio
import json
import logging
import re

from ..bailian.client import BailianLike
from ..schemas import (
    ALL_GOALS,
    ALL_PLATFORMS,
    GOAL_FULL_PACKAGE,
    GOAL_LABELS,
    GenerateRequest,
    Intent,
)

logger = logging.getLogger(__name__)

SYSTEM = """你是跨境上架平台的意图识别器。卖家会写一句诉求，你要判断他想让你做什么。
输出严格的 JSON（不要 markdown 代码块、不要多余文字）：
{
  "goal": "full_package 或 preview",
  "platforms": ["从诉求里明确提到的平台 key"],
  "summary": "一句话复述卖家的诉求",
  "confidence": 0.0 到 1.0
}

goal 的含义（只能二选一）：
- full_package：真的要生成上架包（默认值）。卖家说"帮我出包/上架/铺货/生成 listing"，或没说要什么，都选这个。
- preview：先只要方案、暂时不要生成。卖家说"先别生成/先给我看看你打算怎么做/先出个方案/不着急出包"时选这个。

platforms 只填卖家诉求里**明确点到**的平台，取值必须是：amazon / shopee / aliexpress / lazada / tiktokshop。
卖家没提平台就返回空数组 []，不要猜测、不要默认填全部。

判断原则：拿不准就选 full_package（宁可多给，不可少给）。"""

USER_TMPL = """商品名称：{product_name}
卖家卖点：{selling_points}
卖家诉求：{request_text}

请输出 JSON。"""


def _extract_json(text: str) -> dict:
    """从模型输出里稳健地提取 JSON（与商品理解同一套兜底策略）。"""
    match = re.search(r"\{.*\}", text, re.DOTALL)
    if not match:
        raise ValueError(f"意图识别输出无法解析: {text[:200]}")
    return json.loads(match.group(0))


class IntentAgent:
    def __init__(self, client: BailianLike) -> None:
        self.client = client

    async def run(self, req: GenerateRequest) -> Intent:
        text = (req.request_text or "").strip()
        # 没写诉求：不调模型，直接用默认意图（保持既有请求的行为与耗时不变）
        if not text:
            return Intent(goal=GOAL_FULL_PACKAGE, decided_by="default")
        if self.client.is_mock:
            return Intent(goal=GOAL_FULL_PACKAGE, decided_by="fallback", summary=text[:60])

        try:
            raw = await asyncio.to_thread(
                self.client.chat,
                SYSTEM,
                USER_TMPL.format(
                    product_name=req.product_name or "（未提供）",
                    selling_points=(req.selling_points or "（未提供）")[:400],
                    request_text=text,
                ),
            )
            data = _extract_json(raw)
        except Exception as exc:  # noqa: BLE001 —— 意图判定失败绝不能阻断生成
            logger.warning("意图识别失败，回退完整包: %s", exc)
            return Intent(goal=GOAL_FULL_PACKAGE, decided_by="fallback", summary=text[:60])

        goal = str(data.get("goal", "")).strip()
        if goal not in ALL_GOALS:
            goal = GOAL_FULL_PACKAGE
        # 平台只接受白名单内的 key，且必须非空才生效（空 = 沿用请求里的选择）
        picked = [p for p in (data.get("platforms") or []) if p in ALL_PLATFORMS]
        try:
            conf = float(data.get("confidence", 1.0))
        except (TypeError, ValueError):
            conf = 1.0
        return Intent(
            goal=goal,
            platforms=picked,
            summary=str(data.get("summary", ""))[:120] or text[:60],
            confidence=max(0.0, min(1.0, conf)),
            decided_by="planner",
        )


def describe(intent: Intent) -> str:
    """意图的一句话中文描述（留痕 / 前端展示共用）。"""
    label = GOAL_LABELS.get(intent.goal, intent.goal)
    if intent.platforms:
        return f"{label} · 仅 {len(intent.platforms)} 个平台（诉求中指定）"
    return label
