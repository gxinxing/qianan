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

按问题类型（type）分类，两类严重度完全不同，务必分清：

1. type = "contradiction"（事实矛盾，严重）
   文案的说法与事实档案**直接冲突**。例如：
   - 档案材质是"涤纶"，文案写成"纯棉"
   - 档案容量 300ml，文案写 500ml
   - 档案是"单排扣"，文案写"开衫"（属性张冠李戴）
   - 翻译明显错误导致语义偏差（把"单排扣"译成"单颗纽扣"）

2. type = "unsupported"（证据不足，轻微）
   事实档案**没有提到**，但文案把它当成确定卖点写出来。例如：
   - 档案未提电机参数，文案写"高扭矩电机"
   - 档案未提尺寸，文案写"可放入车载杯架"
   注意：**"档案没写"不等于"事实错误"**，只说明文案超出已有证据。
   这类问题属于营销措辞可优化空间，不影响上架合规。

输出格式（严格 JSON）：
{
  "issues": [
    {"field": "出问题的字段名", "type": "contradiction 或 unsupported",
     "message": "具体问题描述（一句话）", "suggestion": "修改建议"}
  ]
}
如果文案与事实档案完全一致且无夸大，输出 {"issues": []}。
不要重写文案，只报问题。最多输出 5 条最严重的问题。"""


#: 语义审核的严重度映射。
#: 只有「与事实档案直接矛盾」才是阻断级 error。
#: 「无事实支撑的夸大」降为 warn —— 它**没有收敛点**：任何具体表述都可能被判"档案没写"，
#: 一旦当成 error 就会强制触发 revise，改完又出现新的同类表述，形成无限循环
#: （实测 Amazon 单平台空转 11 轮、耗尽 300s 墙钟预算、0 张图产出）。
#: 缺失或无法识别的 type 一律按 warn 处理 —— fail-safe：宁可少阻断，也不要死循环。
_SEVERITY_BY_TYPE = {"contradiction": "error", "unsupported": "warn"}


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
        issue_type = str(item.get("type", "")).strip().lower()
        issues.append(
            ComplianceIssue(
                check_id="semantic_review",
                severity=_SEVERITY_BY_TYPE.get(issue_type, "warn"),
                field=str(item.get("field", "")),
                message=f"[语义审核/{issue_type or 'unknown'}] {item.get('message', '')}",
            )
        )
    return issues
