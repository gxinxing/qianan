"""独立审核 Agent：语义级文案审核（事实一致性/属性张冠李戴/过度夸大）。

与规则引擎互补：规则引擎做确定性校验（长度/禁词/格式），审核 Agent 做语义校验。
对标 mzsleep 的"独立审核 pass"：用不同 system prompt 复核文案与事实档案的一致性。
"""
from __future__ import annotations

import asyncio
import json
import logging

from ..bailian.client import TEXT_MODEL, BailianLike
from ..schemas import ComplianceIssue, PlatformListing, Understanding

logger = logging.getLogger(__name__)

REVIEW_SYSTEM = """你是跨境电商上架文案的独立审核员（不是文案撰写者）。
你的职责是对比「商品事实档案」与「最终文案」，找出语义级问题。

审核维度：
1. 事实不一致：文案中出现的材质、颜色、尺寸、功能等与事实档案矛盾（如事实是"涤纶"却写成"纯棉"）
2. 属性张冠李戴：把 A 属性的值写到 B 属性上（如把"长袖"写成"短袖"，把"单排扣"写成"开衫"）
3. 过度夸大：使用了无事实支撑的绝对化用语或虚假功效宣称（如"100%治愈"、"世界最好"）
4. 语言翻译错误：翻译明显不准确或语义偏差（如把"单排扣"翻译成"单颗纽扣"）

输出格式（严格 JSON）：
{
  "issues": [
    {"field": "出问题的字段名", "message": "具体问题描述（一句话）", "suggestion": "修改建议"}
  ]
}
如果文案与事实档案完全一致且无夸大，输出 {"issues": []}。
不要重写文案，只报问题。"""


async def review_listing(
    client: BailianLike,
    listing: PlatformListing,
    understanding: Understanding,
) -> list[ComplianceIssue]:
    """对单个平台上架包做语义审核，返回发现的 ComplianceIssue 列表。"""

    if client.is_mock:
        return []  # Mock 模式不做语义审核

    facts = understanding.model_dump_json(ensure_ascii=False)
    listing_json = json.dumps(
        {
            "title": listing.title,
            "bullets": listing.bullets,
            "description": listing.description,
            "attributes": listing.attributes,
        },
        ensure_ascii=False,
    )

    user_prompt = f"""请审核以下 {listing.display_name or listing.platform} 平台上架文案。

商品事实档案（唯一事实来源）：
{facts}

待审核文案：
{listing_json}

请逐字段对比，输出严格 JSON。"""

    try:
        raw = await asyncio.to_thread(client.chat, REVIEW_SYSTEM, user_prompt, TEXT_MODEL)
    except Exception as exc:  # noqa: BLE001
        logger.warning("语义审核调用失败（%s）: %s", listing.platform, exc)
        return []

    # 解析 JSON
    try:
        start = raw.find("{")
        if start < 0:
            return []
        data = json.loads(raw[start:])
    except (json.JSONDecodeError, ValueError):
        logger.warning("语义审核输出解析失败（%s）: %s", listing.platform, raw[:200])
        return []

    issues: list[ComplianceIssue] = []
    for item in data.get("issues", []):
        issues.append(
            ComplianceIssue(
                check_id="semantic_review",
                severity="error",
                field=str(item.get("field", "")),
                message=f"[语义审核] {item.get('message', '')}",
            )
        )
    return issues
