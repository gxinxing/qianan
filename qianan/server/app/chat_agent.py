"""对话式 Agent：用 function calling 自主编排上架全流程。

与 run_pipeline（固定管线）不同，chat agent 让模型在对话中自主决定：
先理解商品 → 生成文案 → 审核 → 发现问题自己改 → 出图 → 出视频 → 交付。
全程通过 SSE 事件实时推送"我在做 X"和中间产物，用户可在对话中随时介入。

工具列表：
- understand_product：视觉/文本理解商品
- generate_listing：为指定平台生成文案
- review_listing：规则引擎 + 语义审核
- revise_listing：修订文案
- generate_images：主图 + 详情图
- generate_video：图生视频
- generate_strategy_report：生成策略文档
"""
from __future__ import annotations

import json
import logging
import os
from typing import Any

from . import memory_store
from .agent_core.loop import run_tool_loop
from .agent_core.registry import ToolSpec
from .agent_core.trace import record
from .agents.compliance import ComplianceAgent
from .agents.copywriting import CopywritingAgent
from .agents.review import review_listing
from .agents.rules_engine import RulesEngineAgent
from .agents.understanding import ProductUnderstandingAgent
from .agents.visual import VisualAgent
from .bailian.client import BailianLike, resolve_image_ref
from .schemas import (
    MemoryLesson,
    PlatformListing,
    TaskPlan,
    TaskRecord,
    TaskStatus,
)

logger = logging.getLogger(__name__)

CHAT_SYSTEM = """你是千岸跨境上架 Agent。你的职责是在对话中帮用户完成跨境商品上架的全流程。

你有以下工具可以使用，请根据用户需求自主决定调用顺序：

1. **understand_product** — 理解商品（视觉识别 + 文本分析），返回商品类型/材质/卖点/关键词
2. **generate_listing** — 为指定平台生成上架文案（标题/五点描述/详情/属性/A+模块）
3. **review_listing** — 合规审核（规则引擎确定性校验 + 语义审核事实一致性）
4. **revise_listing** — 根据审核结果修订文案
5. **generate_images** — 生成主图和详情图（以图改图保持商品一致）
6. **generate_video** — 基于主图生成展示视频（图生视频）
7. **submit_deliverable** — 提交最终交付物，结束本轮工作

工作原则：
- 收到商品描述和图片后，先调用 understand_product 理解商品
- 然后为每个目标平台调用 generate_listing 生成文案
- 生成后必须调用 review_listing 审核
- 有 error 必须调用 revise_listing 修订（确定性保证有错必改）
- 修订后再次 review 确认修复
- **提示级问题（warn）不需要修订**：不要为了消除提示反复调用 revise_listing，
  同一平台的修订不要超过 3 轮。改到 2 轮仍报同类问题时，立即停止修订、
  进入出图与交付阶段，把剩余提示留给交付摘要如实披露。
- 文案确认无误后调用 generate_images 和 generate_video
- 全部完成后调用 submit_deliverable 交付
- **出图与交付优先于文案完美**：预算有限时先保证每个平台都有主图并完成交付，
  再考虑措辞优化。绝不可把全部时间花在打磨某一个平台的文案上。
- 每一步都要先用文字告诉用户你在做什么，再调用工具
- 如果用户信息不完整，先询问而不是猜测"""

#: 允许的最大对话工具轮数（每轮可调多个工具）
CHAT_MAX_ROUNDS = 25
#: Agent 总墙钟预算。实测 2 个平台的完整链路（理解+文案+审核+修订+出图）约需 150–250s，
#: 5 个平台需更多；原 300s 会在出图阶段就被耗尽，导致永远交付不了含图的完整包。
#: 取值须留出云函数超时（900s）与单步工具耗时（出图 60s / 视频轮询 300s）的余量。
CHAT_DEADLINE_S = 420

#: 单平台最大自动修订轮数。文案问题理论上"可修"，但模型会反复修出新问题
#: （实测无上限时 Amazon 单平台空转 11 轮、烧光 300s 墙钟、图片 0 张）。
#: 超限即停止修订，剩余问题如实留给交付闸门在交付摘要里披露。
MAX_REVISE_ROUNDS = 3

#: 阻断级 error 中「靠改文案修不掉、只能靠出图解决」的字段。
#: 这类问题无论修订多少轮都修不掉，若纳入闸门会让模型反复 revise 直到超轮数，
#: 因此交给 generate_images 解决，闸门只校验主图是否真的存在。
IMAGE_ONLY_FIELDS = {"mainImage"}


def _platform_requires_bullets(platform: str, rules_map: dict | None) -> bool:
    """该平台是否要求**独立的五点描述**。

    只有 Amazon 要求（rules/amazon.json：count=5）；Shopee / Lazada / AliExpress /
    TikTok Shop 的规则里明确写了 count=0、style="none"，卖点融入描述段落。

    回归背景（2026-09-15 实测）：闸门曾对**所有平台**一律要求 bullets 非空，
    而文案 Agent 的提示词按规则让非 Amazon 平台返回空数组 —— 两边直接打架，
    于是 Shopee 永远被判「缺五点描述」，交付被无限拒绝，Agent 反复重新生成文案
    直到撞上 25 轮上限，5 个平台一个都交付不了。

    未提供 rules_map 时沿用旧行为（要求 bullets）：宁可保守，也不要静默放松判定。
    """
    if not rules_map:
        return True
    rule = (rules_map.get(platform) or {}).get("bullets") or {}
    return int(rule.get("count") or 0) > 0


def evaluate_delivery_gate(
    platforms: list[str],
    listings: dict[str, PlatformListing],
    reviewed: set[str],
    rules_map: dict | None = None,
) -> dict:
    """交付闸门：判定当前状态是否**允许**宣称交付完成。

    设计原则 —— **模型负责选择下一步，代码负责判定这一步是否允许执行。**
    `submit_deliverable` 是唯一能把任务置为 done 的入口，因此「什么叫完成」
    必须由代码判定，不能依赖模型自觉。此前只要 listings 非空就能置 done，
    于是「勾了 5 个平台只做出 2 个」也会在 UI 上显示「已生成完整上架包」。

    阻断项（blockers）非空 → 拒绝 finish，并原样返回给模型让它继续做。
    提示项（warnings）不阻断，但会在交付摘要里如实披露。

    返回 {"ok", "blockers", "warnings", "covered", "requested"}
    """
    blockers: list[str] = []
    warnings: list[str] = []
    covered: list[str] = []

    for p in platforms:
        listing = listings.get(p)
        if listing is None:
            blockers.append(f"{p}：尚未生成任何内容")
            continue

        name = listing.display_name or p
        problems: list[str] = []

        # ① 必需产物完整（标题 / 卖点 / 主图，缺一即不可上架）
        if not (listing.title or "").strip():
            problems.append("缺标题")
        # 五点描述按平台规则判断：只有 Amazon 要求，其余平台卖点融入描述段落
        if _platform_requires_bullets(p, rules_map) and not listing.bullets:
            problems.append("缺五点描述")
        if not listing.images:
            problems.append("缺主图")

        # ② 阻断级合规问题为零
        #    （排除只能靠出图解决的字段，口径与 revise_listing 一致，避免互相打架）
        hard = [
            i for i in (listing.compliance or [])
            if i.severity == "error" and i.field not in IMAGE_ONLY_FIELDS
        ]
        if hard:
            fields = "、".join(dict.fromkeys(i.field for i in hard))
            problems.append(f"{len(hard)} 项阻断级问题（{fields}）")

        # ③ 产物经过审核，且审核结论仍然有效
        #    （reviewed 在 revise 后会被清除，因此这条同时覆盖「审核后又被改过」）
        if p not in reviewed:
            problems.append("尚未通过审核（或审核后又被修改）")

        if problems:
            blockers.append(f"{name}：{'；'.join(problems)}")
        else:
            covered.append(p)
            if not listing.detail_images:
                warnings.append(f"{name}：未生成详情图")
            if not listing.video_url:
                warnings.append(f"{name}：未生成展示视频")
            soft = [i for i in (listing.compliance or []) if i.severity == "warn"]
            if soft:
                warnings.append(f"{name}：{len(soft)} 项提示可后续优化")

    return {
        "ok": not blockers,
        "blockers": blockers,
        "warnings": warnings,
        "covered": covered,
        "requested": list(platforms),
    }


async def run_chat_agent(
    task: TaskRecord,
    client: BailianLike,
    user_message: str,
    on_event=None,
    should_stop=None,
) -> None:
    """对话式 Agent 主循环。

    在对话中自主调用工具完成上架全流程，每一步通过 on_event 推送进度。
    task.listings 在过程中被工具 handler 直接修改（Agent 看到的工具结果和 task 状态同步）。
    """
    req = task.request
    task.status = TaskStatus.running

    # —— 共享状态（工具 handler 通过闭包修改）——
    state: dict[str, Any] = {
        "understanding": None,
        "rules_map": None,
        "listings": {},  # platform -> PlatformListing
        "reviewed": set(),  # 已审核的平台
        "images_done": set(),  # 已生成图片的平台
        "video_done": set(),  # 已生成视频的平台
    }

    rules_agent = RulesEngineAgent()
    copy_agent = CopywritingAgent(client)
    visual_agent = VisualAgent(client)
    compliance = ComplianceAgent()

    image_ref = resolve_image_ref(req.image_url, req.image_base64)

    # ---- 工具定义 ----

    async def tool_understand() -> str:
        """理解商品（视觉+文本），返回结构化信息。"""
        record(task, "build", "understand_product", req.product_name or "(from image)", "理解中...")
        if on_event:
            on_event("text", "让我先看看这个商品...")
        understanding = await ProductUnderstandingAgent(client).run(req, image_ref)
        task.understanding = understanding
        state["understanding"] = understanding
        summary = (
            f"商品类型: {understanding.product_type}\n"
            f"材质: {understanding.material}\n"
            f"卖点: {'; '.join(understanding.selling_points[:5])}\n"
            f"关键词: {', '.join(understanding.keywords[:8])}\n"
            f"目标人群: {understanding.target_audience}"
        )
        record(task, "build", "understand_product", "完成", summary[:120])
        if on_event:
            on_event("text", f"好的，我看了这个商品。它是一个{understanding.product_type}，主要卖点是{'、'.join(understanding.selling_points[:3])}。接下来我来为各平台生成上架文案。")  # noqa: E501
        return summary

    async def tool_generate(platform: str) -> str:
        """为指定平台生成上架文案。platform: amazon / shopee / aliexpress / lazada / tiktokshop"""
        if state["rules_map"] is None:
            state["rules_map"] = rules_agent.run(req.platforms)
        rules = state["rules_map"].get(platform)
        if not rules:
            return f"未知平台: {platform}"

        display = rules.get("displayName", platform)
        record(task, "build", f"generate_listing[{platform}]", display, "生成文案中...")
        if on_event:
            on_event("text", f"正在为{display}生成上架文案...")

        understanding = state["understanding"]
        if understanding is None:
            understanding = await ProductUnderstandingAgent(client).run(req, image_ref)
            task.understanding = understanding
            state["understanding"] = understanding

        # 记忆召回
        memories = memory_store.recall(platform, req.category, k=3)
        if memories:
            memory_store.mark_hit([m["id"] for m in memories])
            task.memory_recall.extend(
                MemoryLesson(
                    lesson=str(m.get("lesson", ""))[:120],
                    platform=platform,
                    hit_count=int(m.get("hit_count", 0)),
                    source_task=str(m.get("source_task", "")),
                )
                for m in memories
            )

        listing = await copy_agent.run(req, understanding, platform, rules, memories=memories)
        state["listings"][platform] = listing
        # 实时同步进 task.listings：周期全量快照(_listing_snapshot)只读 task.listings，
        # 不同步会在生成中途发出空快照，前端整块替换把实时产物冲掉（闪现后消失）。
        task.listings = list(state["listings"].values())
        record(task, "build", f"generate_listing[{platform}]", display, f"标题: {listing.title[:60]}...")

        title_preview = listing.title[:80] if listing.title else "(空)"
        bullets_count = len(listing.bullets)
        if on_event:
            on_event("listing", _listing_detail(listing))
            on_event("text", f"{display}文案已生成。标题：{title_preview}{'...' if len(listing.title) > 80 else ''}，{bullets_count} 条卖点描述。让我检查一下合规性。")  # noqa: E501
        return f"平台: {display}\n标题: {title_preview}\n五点描述: {bullets_count} 条\n描述长度: {len(listing.description)} 字符"  # noqa: E501

    async def tool_review(platform: str) -> str:
        """合规审核：规则引擎（确定性）+ 语义审核（事实一致性）。"""
        listing = state["listings"].get(platform)
        if not listing:
            return f"请先为 {platform} 生成文案。"
        rules = (state["rules_map"] or {}).get(platform, {})
        if not rules:
            state["rules_map"] = rules_agent.run(req.platforms)
            rules = state["rules_map"].get(platform, {})

        display = listing.display_name or platform
        record(task, "heal", f"review_listing[{platform}]", display, "审核中...")
        if on_event:
            on_event("text", f"正在审核{display}的文案合规性...")

        # 规则引擎
        compliance.run(listing, rules, req.category)
        errors = [i for i in listing.compliance if i.severity == "error"]
        warns = [i for i in listing.compliance if i.severity == "warn"]

        # 语义审核
        semantic_issues = []
        if state["understanding"] and not client.is_mock:
            try:
                semantic_issues = await review_listing(client, listing, state["understanding"])
                if semantic_issues:
                    listing.compliance.extend(semantic_issues)
                    # 按严重度分流：只有「与事实档案直接矛盾」才计入阻断级 error。
                    # 曾经无差别 extend 进 errors，于是「无事实支撑的夸大」也被当成 error
                    # 强制 revise —— 而这类问题没有收敛点（改完又出现新的同类表述），
                    # 实测让 Amazon 单平台空转 11 轮、耗尽 300s 预算且 0 张图产出。
                    errors.extend(i for i in semantic_issues if i.severity == "error")
                    warns.extend(i for i in semantic_issues if i.severity != "error")
            except Exception as exc:  # noqa: BLE001
                logger.warning("语义审核失败: %s", exc)

        state["reviewed"].add(platform)
        total_errors = len(errors)
        total_warns = len(warns)

        if total_errors == 0:
            record(task, "heal", f"review_listing[{platform}]", display, f"通过（{total_warns} 项提示）")
            if on_event:
                on_event("text", f"{display}文案审核通过！没有阻断级问题。" + (f" 有 {total_warns} 项提示可后续优化。" if total_warns else ""))  # noqa: E501
            return f"审核通过。{total_warns} 项提示。"
        else:
            error_msgs = "; ".join(f"{i.field}: {i.message}" for i in errors[:5])
            record(task, "heal", f"review_listing[{platform}]", display, f"{total_errors} 项 error", "warn")
            if on_event:
                on_event("text", f"{display}文案发现 {total_errors} 个需要修复的问题：{error_msgs}。我来修改。")
            return f"发现 {total_errors} 个 error：\n{error_msgs}"

    async def tool_revise(platform: str) -> str:
        """修订文案（修复审核发现的问题）。"""
        listing = state["listings"].get(platform)
        if not listing:
            return f"请先为 {platform} 生成文案。"
        rules = (state["rules_map"] or {}).get(platform, {})
        errors = [i for i in listing.compliance if i.severity == "error" and i.field != "mainImage"]
        if not errors:
            return f"{platform} 没有需要修订的 error。"
        # 硬上限：防止模型反复"修出新问题"把整个墙钟预算耗在一个平台上。
        # 超限后把剩余问题交给交付闸门如实披露，而不是继续无谓地烧额度。
        if listing.revised_count >= MAX_REVISE_ROUNDS:
            return (
                f"{platform} 已修订 {listing.revised_count} 轮，达到上限 {MAX_REVISE_ROUNDS} 轮，不再自动修订。"
                "剩余问题属提示/可优化级，不影响上架交付。请继续调用 generate_images 出图，"
                "或直接调用 submit_deliverable 交付。"
            )

        display = listing.display_name or platform
        record(task, "heal", f"revise_listing[{platform}]", display, "修订中...")
        if on_event:
            on_event("text", f"正在修订{display}的文案...")

        revised = await copy_agent.revise(listing, rules, errors)
        revised.revised_count += 1
        state["listings"][platform] = revised
        task.listings = list(state["listings"].values())  # 同步，供周期快照渲染

        # 复检
        compliance.run(revised, rules, req.category)
        remaining = [i for i in revised.compliance if i.severity == "error" and i.field != "mainImage"]

        # 审核状态随产物失效：改过文案后，旧审核结论不再代表当前产物。
        # 复检通过才算重新有效；仍有问题则必须重新走 review。
        if remaining:
            state["reviewed"].discard(platform)
        else:
            state["reviewed"].add(platform)

        record(task, "heal", f"revise_listing[{platform}]", display,
               "全部修复" if not remaining else f"仍有 {len(remaining)} 项 error")
        if on_event:
            on_event("listing", _listing_detail(revised))
            if not remaining:
                on_event("text", f"{display}文案已修订，所有问题已修复！")
            else:
                on_event("text", f"{display}文案已修订，但还有 {len(remaining)} 个问题暂时无法通过文案修改解决。")

        return f"已修订（第 {revised.revised_count} 轮）。" + ("全部修复。" if not remaining else f"仍有 {len(remaining)} 项 error。")  # noqa: E501

    async def tool_images(platform: str) -> str:
        """生成主图和详情图（以图改图）。"""
        listing = state["listings"].get(platform)
        if not listing:
            return f"请先为 {platform} 生成文案。"
        understanding = state["understanding"]
        if not understanding:
            return "请先理解商品。"

        display = listing.display_name or platform
        rules = (state["rules_map"] or {}).get(platform, {})
        record(task, "build", f"generate_images[{platform}]", display, "生成图片中...")
        if on_event:
            on_event("text", f"正在为{display}生成主图和详情图...")

        try:
            await visual_agent.run(understanding, listing, rules, image_ref)
            await visual_agent.run_detail_shots(understanding, listing, image_ref)
            state["images_done"].add(platform)
            imgs = len(listing.images)
            details = len(listing.detail_images)
            record(task, "build", f"generate_images[{platform}]", display, f"{imgs} 主图 + {details} 详情图")
            if on_event:
                on_event("listing", _listing_detail(listing))
                on_event("text", f"{display}图片已生成：{imgs} 张主图 + {details} 张详情图。")
            return f"主图 {imgs} 张，详情图 {details} 张。"
        except Exception as exc:  # noqa: BLE001
            logger.warning("图片生成失败: %s", exc)
            record(task, "build", f"generate_images[{platform}]", display, f"失败: {exc}", "error")
            return f"图片生成失败: {exc}"

    async def tool_video(platform: str) -> str:
        """基于主图生成展示视频。"""
        listing = state["listings"].get(platform)
        if not listing:
            return f"请先为 {platform} 生成文案。"
        if platform not in state["images_done"]:
            return f"请先为 {platform} 生成图片。"
        understanding = state["understanding"]
        if not understanding:
            return "请先理解商品。"

        display = listing.display_name or platform
        record(task, "build", f"generate_video[{platform}]", display, "生成视频中...")
        if on_event:
            on_event("text", f"正在为{display}生成展示视频...")

        try:
            await visual_agent.run_video(understanding, listing)
            state["video_done"].add(platform)
            if listing.video_url:
                record(task, "build", f"generate_video[{platform}]", display, "视频已生成")
                if on_event:
                    on_event("listing", _listing_detail(listing))
                    on_event("text", f"{display}展示视频已生成！")
                return f"视频已生成: {listing.video_url[:60]}..."
            return "视频生成跳过（无主图）。"
        except Exception as exc:  # noqa: BLE001
            logger.warning("视频生成失败: %s", exc)
            return f"视频生成失败: {exc}"

    async def tool_deliver() -> str:
        """提交最终交付物，结束本轮工作。

        这是唯一能把任务置为 done 的入口，因此先过交付闸门：
        任一请求平台未覆盖 / 缺必需产物 / 有阻断级问题 / 未审核，一律拒绝 finish，
        并把缺口原样回给模型，让它继续做而不是假装完成。
        """
        listings = list(state["listings"].values())
        if not listings:
            return "还没有生成任何上架内容。"

        # 闸门按平台规则判断必需产物，因此必须先确保规则已加载
        # （否则会退化成"所有平台都要五点描述"，把非 Amazon 平台永远挡在门外）
        if state["rules_map"] is None:
            state["rules_map"] = rules_agent.run(req.platforms)

        gate = evaluate_delivery_gate(
            req.platforms, state["listings"], state["reviewed"], state["rules_map"]
        )
        if not gate["ok"]:
            task.stage = "交付前校验未通过"
            reason = "；".join(gate["blockers"])
            record(task, "guard", "delivery_gate", "拒绝 finish", reason[:200], "warn")
            if on_event:
                on_event(
                    "text",
                    f"还不能交付，{len(gate['blockers'])} 个平台尚未达标：{reason}。"
                    f"请补齐后再次调用 submit_deliverable。",
                )
            return (
                f"交付未通过校验，不要向用户宣称已完成。缺口如下：{reason}。"
                f"请继续调用相应工具补齐，然后再调用 submit_deliverable。"
            )

        task.listings = listings
        task.status = TaskStatus.done
        task.progress = 1.0
        task.stage = "完成"

        # 反思蒸馏
        try:
            from .agents.reflection import self_reflect
            await self_reflect(task, client)
        except Exception as exc:  # noqa: BLE001
            logger.warning("反思失败: %s", exc)

        platforms_done = [item.display_name or item.platform for item in listings]
        total = len(req.platforms)
        summary = f"已为 {len(listings)}/{total} 个平台生成上架包：{', '.join(platforms_done)}。"
        if len(listings) == total:
            summary += " 全部请求平台均已覆盖，通过合规审核。"
        if state["video_done"]:
            summary += f" {len(state['video_done'])} 个平台已生成展示视频。"
        if gate["warnings"]:
            summary += " 已知不足：" + "；".join(gate["warnings"]) + "。"

        record(task, "reflect", "submit_deliverable", "交付", summary[:120])
        if on_event:
            on_event("done", summary)

        return summary

    # ---- 构建工具注册表 ----
    tools = [
        ToolSpec(
            name="understand_product",
            description="理解商品（视觉识别+文本分析），返回商品类型/材质/卖点/关键词。通常是第一步。",
            parameters={"type": "object", "properties": {}, "required": []},
            handler=tool_understand,
        ),
        ToolSpec(
            name="generate_listing",
            description="为指定平台生成上架文案（标题/五点描述/详情/属性/A+模块）。",
            parameters={
                "type": "object",
                "properties": {
                    "platform": {
                        "type": "string",
                        "description": f"目标平台，可选：{', '.join(req.platforms)}",
                        "enum": req.platforms,
                    }
                },
                "required": ["platform"],
            },
            handler=tool_generate,
        ),
        ToolSpec(
            name="review_listing",
            description="合规审核指定平台的文案（规则引擎确定性校验 + 语义审核事实一致性）。",
            parameters={
                "type": "object",
                "properties": {
                    "platform": {"type": "string", "description": "要审核的平台", "enum": req.platforms},
                },
                "required": ["platform"],
            },
            handler=tool_review,
        ),
        ToolSpec(
            name="revise_listing",
            description="修订指定平台的文案，修复审核发现的问题。",
            parameters={
                "type": "object",
                "properties": {
                    "platform": {"type": "string", "description": "要修订的平台", "enum": req.platforms},
                },
                "required": ["platform"],
            },
            handler=tool_revise,
        ),
        ToolSpec(
            name="generate_images",
            description="为指定平台生成主图和详情图（以图改图保持商品一致）。",
            parameters={
                "type": "object",
                "properties": {
                    "platform": {"type": "string", "description": "目标平台", "enum": req.platforms},
                },
                "required": ["platform"],
            },
            handler=tool_images,
        ),
        ToolSpec(
            name="generate_video",
            description="基于主图为指定平台生成展示视频（图生视频）。",
            parameters={
                "type": "object",
                "properties": {
                    "platform": {"type": "string", "description": "目标平台", "enum": req.platforms},
                },
                "required": ["platform"],
            },
            handler=tool_video,
        ),
        ToolSpec(
            name="submit_deliverable",
            description="提交最终交付物，结束本轮工作。所有平台都完成后调用。",
            parameters={"type": "object", "properties": {}, "required": []},
            handler=tool_deliver,
        ),
    ]

    # ---- 运行 Agent loop ----
    platforms_str = ", ".join(req.platforms)
    user_prompt = (
        f"用户需求：{user_message}\n\n"
        f"商品名称：{req.product_name or '(从图片识别)'}\n"
        f"卖点：{req.selling_points or '(从图片识别)'}\n"
        f"类目：{req.category}\n"
        f"目标平台：{platforms_str}\n"
        f"{'有商品图片' if image_ref else '没有商品图片'}\n\n"
        f"请帮用户完成这些平台的完整上架。"
    )

    # 规划阶段
    task.plan = TaskPlan(strategy="Agent 自主编排", heal_budget=2, focus="", decided_by="chat_agent")
    record(task, "plan", "chat_agent", "对话式 Agent", f"{len(req.platforms)} 平台 · {platforms_str}")

    # 多 Agent 蜂群：一个主控 + 若干执行 agent（平台 worker / 独立 reviewer）。
    # 默认关闭，只有显式开关才走这条路径 —— 演示路径零风险。
    if os.getenv("QIANAN_SWARM") == "1":
        from .agents.swarm import run_swarm

        task.plan.strategy = "多 Agent 蜂群：主控调度 + 平台执行 agent"
        task.plan.decided_by = "swarm_supervisor"
        return await run_swarm(task, client, req, on_event=on_event, should_stop=should_stop)

    if client.is_mock:
        # Mock 模式：跑确定性管线（不经过工具循环），但**完成标准必须与真实模式一致** ——
        # 否则演示时看到的「完成」和真实运行不是同一套判定，等于用 mock 掩盖问题。
        task.stage = "Mock 模式快速生成"
        if on_event:
            on_event("text", "正在快速生成上架内容...")
        from .orchestrator import run_pipeline
        await run_pipeline(task, client)

        gate = evaluate_delivery_gate(
            req.platforms,
            {item.platform: item for item in task.listings},
            {item.platform for item in task.listings if item.compliance_passed},
            RulesEngineAgent().run(req.platforms),
        )
        if not gate["ok"]:
            # 管线产物没达标就不能标 done，哪怕这是 mock
            task.status = TaskStatus.partial
            task.stage = "部分完成（产物未达交付标准）"
            task.error = "；".join(gate["blockers"])[:300]
            record(task, "guard", "delivery_gate", "Mock 流水线产物", task.error, "warn")
            if on_event:
                on_event("done", f"生成结束，但 {len(gate['blockers'])} 个平台未达交付标准，不算完成。")
            return

        if on_event:
            on_event("done", "Mock 模式生成完成")
        return

    stop_check = should_stop or (lambda: False)
    try:
        result = await run_tool_loop(
            client,
            CHAT_SYSTEM,
            user_prompt,
            tools,
            max_rounds=CHAT_MAX_ROUNDS,
            deadline_s=CHAT_DEADLINE_S,
            should_stop=stop_check,
            on_event=lambda name, args, out: record(
                task, "build", name, json.dumps(args, ensure_ascii=False)[:60], out[:120]
            ),
        )

        # 确保最终产物写入 task
        if state["listings"]:
            task.listings = list(state["listings"].values())

        # —— 状态判定的铁律：只有交付闸门放行才可能是 done ——
        # 此前这里无条件 `task.status = TaskStatus.done`，
        # 于是超时 / 超轮数 / 网关异常 / 工具失败都会显示「完成」，UI 上看到的成功不可信。
        if task.status == TaskStatus.done:
            pass  # 已过交付闸门，保持 done
        elif result.get("cancelled") or stop_check():
            task.status = TaskStatus.cancelled
            task.stage = "已取消"
            task.progress = 1.0
            record(task, "guard", "cancelled", "用户取消", result.get("reason", ""), "warn")
            if on_event:
                on_event("done", f"已停止。{len(state['listings'])}/{len(req.platforms)} 个平台已生成的内容已保留。")
        elif result.get("fallback"):
            reason = result.get("reason") or "未收敛"
            if state["listings"]:
                task.status = TaskStatus.partial
                task.stage = f"部分完成（{reason}）"
                task.error = f"未完成全部平台：{reason}"
                record(task, "guard", "partial", f"{len(state['listings'])}/{len(req.platforms)} 平台",
                       f"未收敛：{reason}", "warn")
                if on_event:
                    done_n, total_n = len(state["listings"]), len(req.platforms)
                    on_event(
                        "done",
                        f"只完成了 {done_n}/{total_n} 个平台就中断了（{reason}），未达到交付标准。",
                    )
            else:
                task.status = TaskStatus.failed
                task.stage = f"失败（{reason}）"
                task.error = reason
                record(task, "guard", "failed", "无产物", reason, "warn")
                if on_event:
                    on_event("error", f"生成失败：{reason}")
        else:
            # 循环自然收敛但没有调用 submit_deliverable —— 同样不能算完成
            task.status = TaskStatus.partial
            task.stage = "未交付（循环结束但未提交交付物）"
            task.error = "Agent 未调用 submit_deliverable，产物未经交付闸门校验"
            record(task, "guard", "no_delivery", f"{len(state['listings'])} 平台",
                   "循环收敛但未提交交付物", "warn")
            if on_event:
                on_event("done", "本轮结束，但没有提交交付物（未完成全部平台的校验）。")

        if on_event and result.get("content"):
            on_event("text", result["content"])

    except Exception as exc:  # noqa: BLE001
        logger.exception("chat agent 失败")
        task.status = TaskStatus.failed
        task.error = f"{type(exc).__name__}: {exc}"
        if on_event:
            on_event("error", str(exc))


def _listing_detail(listing: PlatformListing) -> dict:
    """提取 listing 详情供前端展示。"""
    return {
        "type": "listing_update",
        "platform": listing.platform,
        "display_name": listing.display_name,
        "title": listing.title,
        "bullets": listing.bullets,
        "description": listing.description[:300] if listing.description else "",
        "images": listing.images[:3] if listing.images else [],
        "detail_images": listing.detail_images[:4] if listing.detail_images else [],
        "video_url": listing.video_url,
        "compliance_passed": listing.compliance_passed,
        "revised_count": listing.revised_count,
        "compliance_errors": sum(1 for i in listing.compliance if i.severity == "error"),
        "compliance_warns": sum(1 for i in listing.compliance if i.severity == "warn"),
    }
