"""主控 Orchestrator（Agent 运行时版）。

流程：⓪ 规划（模型 function calling，失败回退默认计划）
     ① 商品理解 → ② 规则引擎 → ③④⑤ 每平台并行（文案 + 视觉 + 自愈工具循环）
     → ⑥ 评审 Agent 反思（蒸馏教训入记忆，失败回退模板）→ 聚合。

自愈循环是真 function calling：体检发现问题后由模型决定调用
revise_copy（修订+复检）还是 finish（接受现状），上限由规划的
heal_budget 控制，全任务共享 40s 墙钟预算；任何异常回退旧的一次性修订。
"""
from __future__ import annotations

import asyncio
import json
import logging
import time

from .agent_core.loop import run_tool_loop
from .agent_core.registry import ToolSpec
from .agent_core.trace import record
from .agents.compliance import ComplianceAgent
from .agents.copywriting import CopywritingAgent
from .agents.reflection import self_reflect
from .agents.rules_engine import RulesEngineAgent
from .agents.understanding import ProductUnderstandingAgent
from .agents.visual import VisualAgent
from .bailian.client import BailianLike, resolve_image_ref
from . import memory_store, skill_store
from .schemas import (
    AgentReflection,
    MemoryLesson,
    PlatformListing,
    TaskPlan,
    TaskRecord,
    TaskStatus,
)

logger = logging.getLogger(__name__)

HEAL_WALL_CLOCK_S = 40.0
HEAL_MAX_ROUNDS = 3

PLAN_SYSTEM = """你是千岸跨境上架平台的总调度 Agent。根据商品信息与目标平台，制定本任务的生成策略，并调用 submit_plan 工具提交。
- 若安装了准入类技能工具（如欧盟 GPSR 检查）且商品可能销往对应市场，可先调用该工具获取要点，再把要点写进 focus。
- heal_budget：每平台允许的合规自愈修订轮数（0-3）。卖点带促销/宣称类措辞、类目合规风险高时给 2-3，常规商品给 1。
- focus：一句话生成要点，将注入文案提示词（如「突出便携与续航，避免绝对化用语」）。"""


def _default_plan() -> dict:
    return {
        "strategy": "默认流水线：理解→规则匹配→并行生成→体检自愈",
        "heal_budget": 1,
        "focus": "",
    }


async def plan_task(task: TaskRecord, client: BailianLike) -> dict:
    """⓪ 规划：模型用 submit_plan 工具提交策略；mock/失败均回退默认计划。"""
    req = task.request
    if client.is_mock:
        plan = _default_plan()
        task.plan = TaskPlan(decided_by="fallback", **plan)
        record(task, "plan", "planner", f"{len(req.platforms)} 平台 · mock", "默认计划 · heal_budget=1")
        return plan

    captured: dict = {}

    async def capture(**kwargs) -> str:
        captured.update(kwargs)
        return "计划已收到"

    plan_tool = ToolSpec(
        name="submit_plan",
        description="提交本任务的生成策略计划",
        parameters={
            "type": "object",
            "properties": {
                "strategy": {"type": "string", "description": "一句话整体策略"},
                "heal_budget": {"type": "integer", "description": "每平台自愈修订轮数 0-3"},
                "focus": {"type": "string", "description": "注入文案提示词的生成要点"},
            },
            "required": ["strategy", "heal_budget"],
        },
        handler=capture,
    )
    user = (
        f"商品：{req.product_name}\n卖点：{req.selling_points}\n类目：{req.category}\n"
        f"目标平台：{', '.join(req.platforms)}"
    )
    tools = [plan_tool] + skill_store.skill_tools()
    if len(tools) > 1:
        user += "\n已安装技能工具：" + "、".join(t.name for t in tools[1:])

    research: list[str] = []

    def plan_event(name, args, out):
        if name != "submit_plan":  # submit_plan 在循环结束后单独留痕
            research.append(name)
            record(task, "plan", name, json.dumps(args, ensure_ascii=False)[:60], out[:120])

    res = await run_tool_loop(
        client, PLAN_SYSTEM, user, tools,
        max_rounds=3 if len(tools) > 1 else 2, deadline_s=30.0, on_event=plan_event,
    )
    if res["fallback"] or not captured:
        plan = _default_plan()
        task.plan = TaskPlan(decided_by="fallback", research_tools=research, **plan)
        record(
            task, "plan", "planner", user[:80],
            f"回退默认计划（{res['reason'] or '模型未提交'}）", "fallback",
        )
        return plan
    try:
        budget = int(captured.get("heal_budget", 1))
    except (TypeError, ValueError):
        budget = 1
    plan = {
        "strategy": str(captured.get("strategy", ""))[:200],
        "heal_budget": max(0, min(HEAL_MAX_ROUNDS, budget)),
        "focus": str(captured.get("focus", ""))[:200],
    }
    task.plan = TaskPlan(decided_by="planner", research_tools=research, **plan)
    record(
        task, "plan", "submit_plan", f"{len(req.platforms)} 平台",
        f"策略={plan['strategy'] or '—'} · heal_budget={plan['heal_budget']}",
    )
    return plan


def _collect_errors(listing: PlatformListing, compliance: ComplianceAgent, rules: dict, category: str) -> list:
    """体检并返回可自愈的 error 级问题（主图规格问题修订文案解决不了，不入回路）。"""
    compliance.run(listing, rules, category)
    return [i for i in listing.compliance if i.severity == "error" and i.field != "mainImage"]


async def _heal_listing(
    task: TaskRecord,
    client: BailianLike,
    copy_agent: CopywritingAgent,
    compliance: ComplianceAgent,
    listing: PlatformListing,
    rules: dict,
    category: str,
    budget: int,
    deadline_left: float,
) -> PlatformListing:
    """⑤ 自愈工具循环（真实模式模型决策；mock 确定性脚本；异常回退一次性修订）。"""
    platform = listing.platform
    errors = _collect_errors(listing, compliance, rules, category)
    record(
        task, "heal", f"run_compliance_check[{platform}]", listing.display_name,
        "通过" if not listing.compliance else f"{len(listing.compliance)} 项提示 / {len(errors)} 项 error 可自愈",
    )
    if not errors or budget <= 0:
        return listing

    holder = {"listing": listing}

    def recheck() -> list:
        return _collect_errors(holder["listing"], compliance, rules, category)

    if client.is_mock:
        task.stage = f"自愈修订 {listing.display_name}"
        holder["listing"] = await copy_agent.revise(holder["listing"], rules, errors)
        holder["listing"].revised_count += 1
        left = recheck()
        record(
            task, "heal", f"revise_copy[{platform}]", "mock 脚本",
            "复检通过" if not left else f"仍有 {len(left)} 项 error",
        )
        return holder["listing"]

    async def revise_copy() -> str:
        task.stage = f"自愈修订 {listing.display_name}"
        holder["listing"] = await copy_agent.revise(holder["listing"], rules, errors_ref["items"])
        holder["listing"].revised_count += 1
        errors_ref["items"] = recheck()
        return "已修订并复检。" + ("全部合规问题已修复。" if not errors_ref["items"] else f"仍有 {len(errors_ref['items'])} 项 error：{'; '.join(i.message for i in errors_ref['items'][:3])}")

    async def finish() -> str:
        return "自愈结束，接受当前文案。"

    errors_ref = {"items": errors}
    heal_tools = [
        ToolSpec(
            name="revise_copy",
            description="把当前全部 error 交回文案 Agent 修订，修订后自动复检并返回结果",
            parameters={"type": "object", "properties": {}},
            handler=revise_copy,
        ),
        ToolSpec(
            name="finish",
            description="问题已全部修复或无法通过修订解决时调用，结束自愈",
            parameters={"type": "object", "properties": {}},
            handler=finish,
        ),
    ]
    system = (
        f"你是 {rules.get('displayName', platform)} 平台的合规自愈 Agent。上架文案体检发现 error 级问题，"
        "你可调用 revise_copy 修订（自动复检），确认全部修复或判断无法修复时调用 finish。"
        "不要无意义地反复修订，最多修订到问题清零。"
    )
    user = (
        f"当前 error 清单：\n" + "\n".join(f"- 字段 {i.field}：{i.message}" for i in errors)
        + f"\n\n平台规则要点：\n{RulesEngineAgent.constraint_brief(rules)}"
    )
    res = await run_tool_loop(
        client, system, user, heal_tools,
        max_rounds=budget + 1, deadline_s=max(1.0, deadline_left),
        on_event=lambda name, args, out: record(
            task, "heal", f"{name}[{platform}]", "revise" if name == "revise_copy" else "finish", out[:120]
        ),
    )
    if res["fallback"] and holder["listing"].revised_count == 0:
        # 兜底：循环未收敛且一次都没修订 → 走旧的一次性修订
        try:
            holder["listing"] = await copy_agent.revise(holder["listing"], rules, errors_ref["items"])
            holder["listing"].revised_count += 1
            recheck()
            record(task, "heal", f"revise_copy[{platform}]", f"兜底（{res['reason']}）", "已执行一次性修订", "fallback")
        except Exception as exc:  # noqa: BLE001
            record(task, "heal", f"revise_copy[{platform}]", "兜底修订失败", str(exc)[:100], "error")
    return holder["listing"]


async def run_pipeline(task: TaskRecord, client: BailianLike) -> None:
    req = task.request
    task.status = TaskStatus.running
    try:
        # ⓪ Agent 规划
        plan = await plan_task(task, client)
        task.progress = 0.08

        # ① 商品理解
        task.stage = "商品理解"
        image_ref = resolve_image_ref(req.image_url, req.image_base64)
        understanding = await ProductUnderstandingAgent(client).run(req, image_ref)
        task.understanding = understanding
        task.progress = 0.25

        # ② 规则引擎（非 LLM）
        task.stage = "匹配平台规则"
        rules_map = RulesEngineAgent().run(req.platforms)
        task.progress = 0.3

        # ③④⑤ 每平台并行：文案 + 视觉 + 自愈工具循环
        copy_agent = CopywritingAgent(client)
        visual_agent = VisualAgent(client)
        compliance = ComplianceAgent()
        heal_deadline = time.monotonic() + HEAL_WALL_CLOCK_S

        # 细粒度进度：每个平台拆成 文案 / 主图 / 合规 三阶段，避免进度条长时间卡在 30%
        n_plat = len(req.platforms)
        total_subs = n_plat * 3
        done_subs = 0

        def _advance(name: str, phase: str) -> None:
            nonlocal done_subs
            done_subs += 1
            task.progress = round(0.3 + 0.7 * (done_subs / total_subs), 3)
            task.stage = f"为 {name} {phase}"

        async def build_one(platform: str):
            rules = rules_map[platform]
            name = rules.get("displayName", platform)
            task.stage = f"为 {name} 生成文案"
            memories = memory_store.recall(platform, req.category, k=3)
            if memories:
                memory_store.mark_hit([m["id"] for m in memories])
                # 结构化留存：带历史命中次数，前端可直接展示"这条教训被复用过 N 次"
                task.memory_recall.extend(
                    MemoryLesson(
                        lesson=str(m.get("lesson", ""))[:120],
                        platform=platform,
                        hit_count=int(m.get("hit_count", 0)),
                        source_task=str(m.get("source_task", "")),
                    )
                    for m in memories
                )
                record(
                    task, "build", f"recall_memory[{platform}]", req.category,
                    "；".join(str(m.get("lesson", ""))[:24] for m in memories)[:120],
                )
            listing = await copy_agent.run(
                req, understanding, platform, rules, focus=plan.get("focus", ""), memories=memories
            )
            _advance(name, "生成主图")
            try:
                await visual_agent.run(understanding, listing, rules, image_ref)
            except Exception as exc:  # noqa: BLE001 —— 图片上游渠道不可用时不阻塞该平台文案包
                logger.warning("平台 %s 图片生成失败: %s", platform, exc)
                record(task, "build", f"image_gen[{platform}]", "主图生成", f"失败（网关渠道不可用）: {exc}", "error")
            _advance(name, "自检合规")
            listing = await _heal_listing(
                task, client, copy_agent, compliance, listing, rules, req.category,
                budget=plan.get("heal_budget", 1),
                deadline_left=heal_deadline - time.monotonic(),
            )
            _advance(name, "已就绪")
            return listing

        task.listings = await asyncio.gather(*(build_one(p) for p in req.platforms))

        # ⑥ 评审 Agent 反思：对比事实档案与输出，蒸馏教训入记忆（失败回退模板）
        await self_reflect(task, client)

        task.stage = "完成"
        task.progress = 1.0
        task.status = TaskStatus.done
    except Exception as exc:  # noqa: BLE001 —— Demo 阶段全量捕获，保证任务有终态
        logger.exception("pipeline 失败")
        task.status = TaskStatus.failed
        task.error = f"{type(exc).__name__}: {exc}"
