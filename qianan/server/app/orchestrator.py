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
from .agents.intent import IntentAgent, describe as describe_intent
from .agents.reflection import self_reflect
from .agents.review import review_listing
from .agents.rules_engine import RulesEngineAgent
from .agents.understanding import ProductUnderstandingAgent
from .agents.visual import VisualAgent
from .bailian.client import BailianLike, resolve_image_ref
from . import memory_store, skill_store
from .schemas import (
    ACTION_LABELS,
    ALL_ACTIONS,
    GOAL_LABELS,
    GOAL_PREVIEW,
    OPTIONAL_ACTIONS,
    AgentReflection,
    MemoryLesson,
    PlatformListing,
    TaskPlan,
    TaskRecord,
    TaskStatus,
    Understanding,
    actions_for_goal,
)

logger = logging.getLogger(__name__)

HEAL_WALL_CLOCK_S = 40.0
HEAL_MAX_ROUNDS = 3

PLAN_SYSTEM = """你是千岸跨境上架平台的总调度 Agent。根据商品信息与目标平台，制定本任务的生成策略，并调用 submit_plan 工具提交。
- 若安装了准入类技能工具（如欧盟 GPSR 检查）且商品可能销往对应市场，可先调用该工具获取要点，再把要点写进 focus。
- heal_budget：每平台允许的合规自愈修订轮数（0-3）。卖点带促销/宣称类措辞、类目合规风险高时给 2-3，常规商品给 1。
- focus：一句话生成要点，将注入文案提示词（如「突出便携与续航，避免绝对化用语」）。
- skip：本次要跳过的**可选动作**数组，只能从 generate_detail_shots、generate_video 里选。
  · generate_detail_shots = 每平台 4 张多角度详情图（正面全貌 / 材质特写 / 使用场景 / 平铺搭配）。适合服饰、家居等需要展示细节与质感的商品；结构单一的小工具、配件，跳过它交付更快。
  · generate_video = 每平台 1 条 5 秒展示视频。适合需要动态展示卖点的商品；纯功能性、外观无看点的商品可跳过。
  这两个动作是本次任务最耗时的环节，跳过能明显缩短交付时间——**该跳就跳，但别为了快牺牲商品的表达能力**。
  其余动作（商品理解 / 规则匹配 / 文案 / 主图 / 合规体检 / 反思）是强制动作，不接受跳过，填了也会被忽略。"""


def _default_plan() -> dict:
    return {
        "strategy": "默认流水线：理解→规则匹配→并行生成→体检自愈",
        "heal_budget": 1,
        "focus": "",
        "skip": [],
    }


def filter_skip_request(requested) -> tuple[list[str], list[str]]:
    """policy 层：把规划器请求的跳过项拆成 (接受, 拒绝)。

    只有 OPTIONAL_ACTIONS 内的动作可被跳过；强制动作（合规体检、主图、文案等）
    一律拒绝 —— 这条不依赖 prompt 自律，是硬约束。
    """
    req = {str(s).strip() for s in (requested or []) if str(s).strip()}
    accepted = sorted(req & set(OPTIONAL_ACTIONS))
    refused = sorted(req - set(OPTIONAL_ACTIONS))
    return accepted, refused


def resolve_skip(plan: dict, ablation=None, allowed: set[str] | None = None) -> list[str]:
    """把规划声明的跳过项解析为本次任务实际生效的跳过列表。

    `allowed` 是意图划定的动作空间：不在其中的动作根本没进执行图，
    因此不该算作「规划跳过」—— 两者的证据分开记（skipped vs excluded）。

    `ablation.force_skip` 是验证通道：绕过规划器强制跳过，
    用于证明"执行器确实消费了规划"（若强制跳过耗时没有下降，说明规划是摆设）。
    """
    forced = getattr(ablation, "force_skip", None) if ablation is not None else None
    accepted, _ = filter_skip_request(forced or (plan or {}).get("skip"))
    if allowed is not None:
        accepted = [a for a in accepted if a in allowed]
    return accepted


def excluded_actions(goal: str) -> list[str]:
    """本次意图不包含的动作（相对完整动作空间）—— 意图改变执行图的直接证据。"""
    space = actions_for_goal(goal)
    return [a for a in ALL_ACTIONS if a not in space]


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
                "skip": {
                    "type": "array",
                    "items": {"type": "string", "enum": list(OPTIONAL_ACTIONS)},
                    "description": (
                        "本次任务要跳过的可选动作。可选值：generate_detail_shots（4 张多角度详情图）、"
                        "generate_video（5 秒展示视频）。商品结构简单或需尽快出包时跳过可显著缩短交付时间。"
                    ),
                },
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
    # ---- policy 层：只接受 OPTIONAL_ACTIONS 内的跳过项，强制动作一律忽略 ----
    skip, refused = filter_skip_request(captured.get("skip"))
    if refused:
        record(
            task, "plan", "skip_rejected", "、".join(refused),
            "强制动作不接受跳过，已忽略", "warn",
        )
    plan = {
        "strategy": str(captured.get("strategy", ""))[:200],
        "heal_budget": max(0, min(HEAL_MAX_ROUNDS, budget)),
        "focus": str(captured.get("focus", ""))[:200],
        "skip": skip,
    }
    task.plan = TaskPlan(decided_by="planner", research_tools=research, **plan)
    skip_note = f" · 跳过={'、'.join(ACTION_LABELS.get(s, s) for s in skip)}" if skip else ""
    record(
        task, "plan", "submit_plan", f"{len(req.platforms)} 平台",
        f"策略={plan['strategy'] or '—'} · heal_budget={plan['heal_budget']}{skip_note}",
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
    understanding=None,
) -> PlatformListing:
    """⑤ 确定性强制自愈 + 语义审核 + Agent 自主迭代。

    闭环设计（对标 mzsleep "生成→审核→修订→保存"确定性管线）：
    1. 规则引擎体检 → 收集 error
    2. 有 error → 强制修订一轮（确定性，不经过模型决策，保证有错必改）
    3. 独立语义审核（事实一致性 / 属性张冠李戴 / 过度夸大）
    4. 仍有问题且 budget > 1 → 进入 Agent tool loop 自主迭代
    5. 任何异常回退一次性修订兜底。
    """
    platform = listing.platform
    errors = _collect_errors(listing, compliance, rules, category)
    record(
        task, "heal", f"run_compliance_check[{platform}]", listing.display_name,
        "通过" if not listing.compliance else f"{len(listing.compliance)} 项提示 / {len(errors)} 项 error 可自愈",
    )

    holder = {"listing": listing}

    def recheck() -> list:
        return _collect_errors(holder["listing"], compliance, rules, category)

    if not errors or budget <= 0:
        # 规则引擎通过，但仍跑语义审核（对标 mzsleep 独立审核 pass）
        if understanding and not client.is_mock and deadline_left > 5:
            semantic_issues = await review_listing(client, holder["listing"], understanding)
            if semantic_issues:
                record(
                    task, "heal", f"semantic_review[{platform}]", "独立语义审核",
                    f"发现 {len(semantic_issues)} 项语义问题", "warn",
                )
                holder["listing"].compliance.extend(semantic_issues)
                try:
                    holder["listing"] = await copy_agent.revise(holder["listing"], rules, semantic_issues)
                    holder["listing"].revised_count += 1
                    compliance.run(holder["listing"], rules, category)
                    record(task, "heal", f"revise_copy[{platform}]", "语义问题强制修订", "已修订并复检")
                except Exception as exc:  # noqa: BLE001
                    logger.warning("语义审核修订失败（%s）: %s", platform, exc)
        return holder["listing"]

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

    # ---- 第一轮：确定性强制修订（有 error 必修，不经过模型决策）----
    task.stage = f"确定性修订 {listing.display_name}"
    try:
        holder["listing"] = await copy_agent.revise(holder["listing"], rules, errors)
        holder["listing"].revised_count += 1
        errors_ref = {"items": recheck()}
        record(
            task, "heal", f"revise_copy[{platform}]", "强制修订（第1轮）",
            "全部修复" if not errors_ref["items"] else f"仍有 {len(errors_ref['items'])} 项 error",
        )
    except Exception as exc:  # noqa: BLE001
        logger.warning("强制修订失败（%s）: %s", platform, exc)
        errors_ref = {"items": errors}

    # ---- 独立语义审核（对标 mzsleep 核心亮点）----
    if understanding and deadline_left > 5:
        try:
            semantic_issues = await review_listing(client, holder["listing"], understanding)
            if semantic_issues:
                record(
                    task, "heal", f"semantic_review[{platform}]", "独立语义审核",
                    f"发现 {len(semantic_issues)} 项语义问题", "warn",
                )
                errors_ref["items"] = errors_ref["items"] + semantic_issues
                holder["listing"].compliance.extend(semantic_issues)
        except Exception as exc:  # noqa: BLE001
            logger.warning("语义审核异常（%s）: %s", platform, exc)

    # ---- 第二轮起：Agent 自主迭代（概率性收敛）----
    remaining = errors_ref["items"]
    if not remaining or budget <= 1 or deadline_left <= 3:
        return holder["listing"]

    async def revise_copy() -> str:
        task.stage = f"Agent 自愈迭代 {listing.display_name}"
        holder["listing"] = await copy_agent.revise(holder["listing"], rules, errors_ref["items"])
        holder["listing"].revised_count += 1
        errors_ref["items"] = recheck()
        return "已修订并复检。" + ("全部合规问题已修复。" if not errors_ref["items"] else f"仍有 {len(errors_ref['items'])} 项 error：{'; '.join(i.message for i in errors_ref['items'][:3])}")

    async def finish() -> str:
        return "自愈结束，接受当前文案。"

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
        f"当前 error 清单：\n" + "\n".join(f"- 字段 {i.field}：{i.message}" for i in errors_ref["items"])
        + f"\n\n平台规则要点：\n{RulesEngineAgent.constraint_brief(rules)}"
    )
    res = await run_tool_loop(
        client, system, user, heal_tools,
        max_rounds=budget, deadline_s=max(1.0, deadline_left),
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


async def _generate_strategy_report(
    task: TaskRecord, client: BailianLike, plan: dict, understanding: Understanding
) -> str:
    """生成用户可读的上新策略报告（对标 mzsleep 策略文档交付物）。"""
    if client.is_mock:
        return "## 上新策略报告（Mock）\n\n商品理解完成，策略已执行，文案已生成并通过合规检查。"

    platforms_str = ", ".join(task.request.platforms)
    system = """你是跨境电商上新策略分析师。根据以下信息输出一份简明的《上新策略报告》（Markdown）：
    1. **商品理解摘要**：商品类型、核心材质、关键卖点
    2. **平台适配策略**：每个目标平台的差异化要点
    3. **合规风险点**：已识别的合规注意事项
    4. **已知不足**：当前生成方案的局限性
    5. **优化建议**：后续可改进的方向

    要求：简洁、专业、可执行，总长度 ≤800 字。"""
    skipped = [ACTION_LABELS.get(a, a) for a in (plan.get("skip") or [])]
    user = (
        f"商品名称：{task.request.product_name}\n"
        f"目标平台：{platforms_str}\n"
        f"商品理解：{understanding.model_dump_json(ensure_ascii=False)}\n"
        f"规划策略：{plan.get('strategy', '—')}\n"
        f"生成要点：{plan.get('focus', '—')}\n"
        f"自愈预算：{plan.get('heal_budget', 1)} 轮\n"
        f"本次跳过的生成环节：{('、'.join(skipped)) if skipped else '无（完整流水线）'}"
        + ("\n\n注意：上述被跳过的环节本次没有产出物，写「已知不足」时请如实说明，不要描述不存在的内容。"
           if skipped else "")
    )
    import asyncio as _aio
    return await _aio.to_thread(client.chat, system, user)


async def run_pipeline(task: TaskRecord, client: BailianLike) -> None:
    req = task.request
    abl = req.ablation  # Optional[AblationConfig], None = 完整管线
    task.status = TaskStatus.running
    try:
        # ⓪a 输入理解②：意图 —— 决定本次动作空间（未写诉求时不调模型，零额外成本）
        intent = await IntentAgent(client).run(req)
        if intent.platforms:
            # 诉求里明确点名了平台 → 覆盖请求里的选择（卖家说的算）
            req.platforms = intent.platforms
        intent.excluded_actions = excluded_actions(intent.goal)
        task.intent = intent
        record(
            task, "plan", "understand_intent",
            req.request_text[:60] or "（未写诉求，按完整包处理）",
            describe_intent(intent) + (f" · 置信度 {intent.confidence:.2f}" if intent.decided_by == "planner" else ""),
            "fallback" if intent.decided_by == "fallback" else "ok",
        )
        task.progress = 0.04

        # ⓪b Agent 规划（在意图划定的动作空间内选路）
        if abl and abl.disable_plan:
            plan = _default_plan()
            task.plan = TaskPlan(decided_by="ablated", **plan)
            record(task, "plan", "planner", "ABLATED", "规划阶段已消融 · 使用默认计划", "ablated")
        else:
            plan = await plan_task(task, client)
        task.progress = 0.08

        # ⓪c 消费规划与意图 —— "执行图被改变"的两条来源，分开留痕：
        #    excluded = 意图不包含的动作；skipped = 规划决定跳过的动作。
        allowed = actions_for_goal(intent.goal)
        applied_skip = resolve_skip(plan, abl, allowed)
        if task.plan is not None:
            task.plan.skipped_actions = applied_skip
        if applied_skip:
            record(
                task, "plan", "skip_actions",
                "、".join(ACTION_LABELS.get(a, a) for a in applied_skip),
                "已从执行图移除，本任务不再执行这些步骤", "ok",
            )
        if intent.excluded_actions:
            record(
                task, "plan", "exclude_actions",
                "、".join(ACTION_LABELS.get(a, a) for a in intent.excluded_actions),
                f"本次意图「{GOAL_LABELS.get(intent.goal, intent.goal)}」不包含这些步骤", "ok",
            )
        do_detail_shots = "generate_detail_shots" not in applied_skip
        do_video = "generate_video" not in applied_skip

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

        # 【意图：方案预览】读懂商品 + 匹配规则即止 —— 产出上新策略报告，不生成上架物料。
        # 不产出上架包 ⇒ 没有可上架的东西 ⇒ 合规体检与反思不适用于本次意图
        # （guardrail 保护的是「要上架的产物」，不是流程本身）。
        if intent.goal == GOAL_PREVIEW:
            task.stage = "生成上新策略"
            try:
                task.strategy_report = await _generate_strategy_report(task, client, plan, understanding)
                record(task, "plan", "strategy_report", "上新策略报告", "已生成（方案预览，未生成上架物料）", "ok")
            except Exception as exc:  # noqa: BLE001
                logger.warning("策略报告生成失败: %s", exc)
            task.stage = "方案已就绪"
            task.progress = 1.0
            task.status = TaskStatus.done
            return

        # ③④⑤ 每平台并行：文案 + 视觉 + 自愈工具循环
        copy_agent = CopywritingAgent(client)
        visual_agent = VisualAgent(client)
        compliance = ComplianceAgent()
        heal_deadline = time.monotonic() + HEAL_WALL_CLOCK_S

        # 细粒度进度：每个平台拆成 文案 / 主图+详情图+视频 / 合规 三阶段
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
            use_memory = not (abl and abl.disable_memory)
            memories = memory_store.recall(platform, req.category, k=3) if use_memory else []
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
                record(
                    task, "build", f"recall_memory[{platform}]", req.category,
                    "；".join(str(m.get("lesson", ""))[:24] for m in memories)[:120],
                )
            listing = await copy_agent.run(
                req, understanding, platform, rules, focus=plan.get("focus", ""), memories=memories
            )
            _advance(name, "生成视觉素材")
            try:
                await visual_agent.run(understanding, listing, rules, image_ref)
                # 详情图 + 视频是否执行，由规划器的 skip 决定（不阻塞主流程）
                if do_detail_shots:
                    await visual_agent.run_detail_shots(understanding, listing, image_ref)
                if do_video:
                    await visual_agent.run_video(understanding, listing)
                if listing.video_url:
                    record(task, "build", f"video_gen[{platform}]", "图生视频", f"视频已生成: {listing.video_url[:60]}")
                if listing.detail_images:
                    record(task, "build", f"detail_images[{platform}]", f"{len(listing.detail_images)} 张详情图", "已生成")
            except Exception as exc:  # noqa: BLE001
                logger.warning("平台 %s 视觉素材生成失败: %s", platform, exc)
                record(task, "build", f"visual[{platform}]", "视觉素材生成", f"部分失败: {exc}", "error")
            _advance(name, "自检合规")
            if abl and abl.disable_heal:
                compliance.run(listing, rules, req.category)
                record(task, "heal", f"run_compliance_check[{platform}]", listing.display_name,
                       f"消融模式 · {len(listing.compliance)} 项提示（不自愈）", "ablated")
            else:
                listing = await _heal_listing(
                    task, client, copy_agent, compliance, listing, rules, req.category,
                    budget=plan.get("heal_budget", 1),
                    deadline_left=heal_deadline - time.monotonic(),
                    understanding=understanding,
                )
            _advance(name, "已就绪")
            return listing

        task.listings = await asyncio.gather(*(build_one(p) for p in req.platforms))

        # ⑥ 生成上新策略报告（用户可读交付物，对标 mzsleep 策略文档）
        if not (abl and abl.disable_plan):
            try:
                task.strategy_report = await _generate_strategy_report(task, client, plan, understanding)
                record(task, "plan", "strategy_report", "上新策略报告", "已生成", "ok")
            except Exception as exc:  # noqa: BLE001
                logger.warning("策略报告生成失败: %s", exc)

        # ⑦ 评审 Agent 反思：对比事实档案与输出，蒸馏教训入记忆（失败回退模板）
        if abl and abl.disable_reflect:
            record(task, "reflect", "self_reflect", "ABLATED", "反思阶段已消融 · 不回写记忆", "ablated")
        else:
            await self_reflect(task, client)

        task.stage = "完成"
        task.progress = 1.0
        task.status = TaskStatus.done
    except Exception as exc:  # noqa: BLE001 —— Demo 阶段全量捕获，保证任务有终态
        logger.exception("pipeline 失败")
        task.status = TaskStatus.failed
        task.error = f"{type(exc).__name__}: {exc}"
