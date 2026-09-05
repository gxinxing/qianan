"""进化 Agent：分析记忆/反馈/自愈指标 → 产出提案（附证据）→ 人审 → 应用或回滚。

提案类型白名单：
- prompt_patch：给文案系统提示词追加一条生成规则（写 prompts/*.md 新版本，可回滚）
- rule_patch：给平台规则库追加禁词（写 evolution/overlays，rules_store 读取时合并，可回滚）

诚实边界：所有提案必须附证据条目，人工批准后才生效；无证据时不产出提案。
"""
from __future__ import annotations

import json
import logging
import threading
import os
import time
import uuid
from pathlib import Path

from .. import collector, memory_store, prompt_store
from ..agent_core.loop import run_tool_loop
from ..agent_core.registry import ToolSpec
from ..bailian.client import BailianLike
from ..rules_store import cache_clear
from ..schemas import ALL_PLATFORMS

logger = logging.getLogger(__name__)


def _resolve_evolution_dir() -> Path:
    """定位 data/evolution：env 优先，其次向上回退两级探测（兼容云函数只读布局）。"""
    env = os.getenv("QIANAN_EVOLUTION_DIR", "")
    if env:
        return Path(env)
    here = Path(__file__).resolve()
    for cand in (here.parents[2] / "data" / "evolution", here.parents[1] / "data" / "evolution"):
        if cand.is_dir():
            return cand
    return here.parents[1] / "data" / "evolution"


DATA_DIR = _resolve_evolution_dir()
PROPOSALS_FILE = DATA_DIR / "proposals.jsonl"
OVERLAYS_DIR = DATA_DIR / "overlays"

PROMPT_TARGETS = {"copywriting_system", "copywriting_revise_system"}
RULE_GROUPS = {"claims", "promotional", "regulatory", "restricted"}

_LOCK = threading.Lock()

SYSTEM = """你是千岸跨境上架平台的进化 Agent，负责基于积累的记忆、用户反馈与上架后经营数据持续改进生成质量。
分析证据，产出恰好一条可立即落地的改进提案，并调用 submit_proposal 工具提交。
证据源（三类，按业务信号强度排序）：
1. 经营数据异常：已上架商品的 CTR 跌破基线（0.02）。标题质量分低的商品 CTR 系统性偏低——
   此类证据优先产出 prompt_patch，规则方向：标题须含品牌词 + 核心规格数字，长度 60~170 字符，关键词丰富。
2. 自愈教训：合规引擎修订记录沉淀的经验。
3. 用户差评反馈。
提案类型（二选一）：
1. prompt_patch：给文案系统提示词追加一条生成规则。target ∈ [copywriting_system, copywriting_revise_system]；change = {"append": "一句话规则，不超过60字，写成『遇到X时应Y』"}。
2. rule_patch：给平台规则库追加禁用词。target = 平台 id（amazon/shopee/aliexpress/lazada/tiktokshop）；change = {"group": "claims|promotional|regulatory|restricted", "words": ["禁词1"]}。
要求：reason 说明依据哪条证据；evidence 列出支撑证据原文（不超过3条，每条不超过100字）。
证据不足以支撑任何改进时，不要提交提案，直接结束。"""


# ---------- 提案存取 ----------

def _read_all() -> list[dict]:
    if not PROPOSALS_FILE.exists():
        return []
    rows: list[dict] = []
    for line in PROPOSALS_FILE.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            rows.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    return rows


def _write_all(rows: list[dict]) -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    with _LOCK:
        with open(PROPOSALS_FILE, "w", encoding="utf-8") as f:
            for r in rows:
                f.write(json.dumps(r, ensure_ascii=False) + "\n")


def list_proposals(limit: int = 100) -> list[dict]:
    rows = _read_all()
    rows.sort(key=lambda r: r.get("ts", 0), reverse=True)
    return rows[:limit]


def _proposal(ptype: str, target: str, change: dict, reason: str, evidence: list) -> dict:
    return {
        "id": "p-" + uuid.uuid4().hex[:8],
        "ts": time.time(),
        "status": "pending",
        "type": ptype,
        "target": target,
        "change": change,
        "reason": reason,
        "evidence": evidence,
        "decided_at": None,
    }


# ---------- 进化分析 ----------

async def evolve(client: BailianLike, heal_stats: list[dict] | None = None) -> dict:
    """分析一轮：有证据才产提案。返回 {generated, proposal?/reason?}。

    证据三源（PRD v0.3 · Feature 4）：自愈教训 / 用户差评 / 上架后经营数据异常。
    """
    exps = memory_store.list_experiences()[:20]
    fbs = [f for f in memory_store.list_feedback() if f.get("rating") == -1][:10]
    metric_anomalies = collector.anomalies()[:10]
    if not exps and not fbs and not metric_anomalies:
        return {"generated": 0, "reason": "暂无证据（还没有记忆条目、差评反馈或经营数据异常）"}

    if client.is_mock:
        raw = _mock_propose(exps, fbs, metric_anomalies)
    else:
        raw = await _llm_propose(client, exps, fbs, heal_stats or [], metric_anomalies)
    if not raw:
        return {"generated": 0, "reason": "本轮分析未产出可落地的改进提案"}
    if _duplicate_pending(raw):
        return {"generated": 0, "reason": "相同提案已在审批队列中，跳过重复产出"}
    p = _proposal(raw["type"], raw["target"], raw["change"], raw["reason"], raw["evidence"])
    rows = _read_all()
    rows.append(p)
    _write_all(rows)
    return {"generated": 1, "proposal": p}


def _duplicate_pending(raw: dict) -> bool:
    """同一异常反复分析会产相同提案：pending 队列已存在则跳过（审批队列不膨胀）。"""
    sig = json.dumps(raw.get("change") or {}, sort_keys=True, ensure_ascii=False)
    for r in _read_all():
        if r.get("status") != "pending":
            continue
        if r.get("type") == raw.get("type") and r.get("target") == raw.get("target"):
            if json.dumps(r.get("change") or {}, sort_keys=True, ensure_ascii=False) == sig:
                return True
    return False


def _mock_propose(exps: list[dict], fbs: list[dict], metric_anomalies: list[dict] | None = None) -> dict | None:
    """确定性提案：经营异常（业务信号最强）→ 命中频次最高的教训 → 最新差评。"""
    metric_anomalies = metric_anomalies or []
    if metric_anomalies:
        worst = min(metric_anomalies, key=lambda r: r.get("ctr", 1.0))
        return {
            "type": "prompt_patch",
            "target": "copywriting_system",
            "change": {"append": "遇到标题生成时应包含品牌词与核心规格数字，长度 60~170 字符、关键词丰富"},
            "reason": "上架后经营数据回流显示 CTR 跌破基线，低质量标题系统性拉低点击",
            "evidence": [
                f"SKU {worst.get('sku')}：CTR {worst.get('ctr')}（基线 0.02），曝光 {worst.get('impressions')}，标题质量分 {worst.get('title_quality')}",
            ],
        }
    if exps:
        top = max(exps, key=lambda e: (e.get("hit_count", 0), e.get("ts", 0)))
        lesson = str(top.get("lesson", "")).strip()[:60]
        if lesson:
            return {
                "type": "prompt_patch",
                "target": "copywriting_system",
                "change": {"append": lesson},
                "reason": "来自命中频次最高的自愈教训，注入提示词可避免重蹈覆辙",
                "evidence": [f"教训 {top.get('id', '')}（命中 {top.get('hit_count', 0)} 次）：{lesson}"],
            }
    if fbs:
        fb = fbs[0]
        comment = str(fb.get("comment", "")).strip()[:40] or "整体不满意"
        return {
            "type": "prompt_patch",
            "target": "copywriting_system",
            "change": {"append": f"规避用户差评指出的问题：{comment}"},
            "reason": "来自最新一条差评反馈",
            "evidence": [f"差评（{fb.get('platform', '')} / {fb.get('task_id', '')}）：{comment}"],
        }
    return None


async def _llm_propose(
    client: BailianLike,
    exps: list[dict],
    fbs: list[dict],
    heal_stats: list[dict],
    metric_anomalies: list[dict] | None = None,
) -> dict | None:
    captured: dict = {}

    async def submit_proposal(**kwargs) -> str:
        captured.update(kwargs)
        return "提案已收到，等待人工审批"

    tool = ToolSpec(
        name="submit_proposal",
        description="提交一条改进提案（类型 + 目标 + 变更 + 理由 + 证据）",
        parameters={
            "type": "object",
            "properties": {
                "type": {"type": "string", "enum": ["prompt_patch", "rule_patch"]},
                "target": {"type": "string", "description": "prompt 名或平台 id"},
                "change": {"type": "object", "description": "变更内容"},
                "reason": {"type": "string"},
                "evidence": {"type": "array", "items": {"type": "string"}},
            },
            "required": ["type", "target", "change", "reason", "evidence"],
        },
        handler=submit_proposal,
    )
    lines = ["上架后经营数据异常（CTR 跌破基线 0.02）："]
    anomalies = metric_anomalies or []
    lines += [
        f"- SKU {a.get('sku')}（{a.get('platform', '')}）：CTR {a.get('ctr')}，曝光 {a.get('impressions')}，标题质量分 {a.get('title_quality')}"
        for a in anomalies[:6]
    ] or ["- （无）"]
    lines.append("历史自愈教训（experiences）：")
    lines += [
        f"- [{e.get('platform', '')}/{e.get('category', '')}] 命中 {e.get('hit_count', 0)} 次：{e.get('lesson', '')}"
        for e in exps[:10]
    ] or ["- （无）"]
    lines.append("用户差评反馈：")
    lines += [
        f"- {f.get('platform', '')}（任务 {str(f.get('task_id', ''))[:8]}）：{f.get('comment', '') or '（无文字）'}"
        for f in fbs[:6]
    ] or ["- （无）"]
    if heal_stats:
        recent = heal_stats[-5:]
        lines.append(
            "最近任务自愈情况："
            + "；".join(f"{t.get('product_name', '')[:12]} 修订 {t.get('revised', 0)} 次" for t in recent)
        )
    user = "\n".join(lines) + "\n\n请基于以上证据提交恰好一条改进提案。"
    res = await run_tool_loop(client, SYSTEM, user, [tool], max_rounds=2, deadline_s=30.0)
    if res["fallback"] or not captured:
        logger.info("进化分析未产出提案（%s）", res["reason"] or "模型未提交")
        return None
    return _normalize(captured)


def _normalize(raw: dict) -> dict | None:
    """白名单校验模型提案；任何字段非法都丢弃（宁缺毋滥）。"""
    ptype = raw.get("type")
    target = str(raw.get("target", ""))
    change = raw.get("change") or {}
    if not isinstance(change, dict):
        return None
    if ptype == "prompt_patch":
        if target not in PROMPT_TARGETS:
            return None
        append = str(change.get("append", "")).strip()[:80]
        if not append:
            return None
        change = {"append": append}
    elif ptype == "rule_patch":
        if target not in ALL_PLATFORMS:
            return None
        group = str(change.get("group", "claims"))
        if group not in RULE_GROUPS:
            return None
        words = [str(w).strip().lower() for w in (change.get("words") or []) if str(w).strip()][:5]
        if not words:
            return None
        change = {"group": group, "words": words}
    else:
        return None
    reason = str(raw.get("reason", "")).strip()[:200]
    evidence = [str(e)[:100] for e in (raw.get("evidence") or []) if str(e).strip()][:3]
    if not reason or not evidence:
        return None
    return {"type": ptype, "target": target, "change": change, "reason": reason, "evidence": evidence}


# ---------- 人审：批准 / 驳回 / 回滚 ----------

def _find(pid: str) -> tuple[list[dict], dict | None]:
    rows = _read_all()
    return rows, next((r for r in rows if r.get("id") == pid), None)


def approve(pid: str) -> tuple[bool, str]:
    rows, p = _find(pid)
    if p is None:
        return False, "提案不存在"
    if p.get("status") != "pending":
        return False, f"提案当前状态为 {p.get('status')}，不可批准"
    try:
        detail = _apply(p)
    except Exception as exc:  # noqa: BLE001
        logger.exception("提案应用失败")
        return False, f"应用失败: {exc}"
    p["status"] = "applied"
    p["decided_at"] = time.time()
    _write_all(rows)
    return True, detail


def reject(pid: str) -> tuple[bool, str]:
    rows, p = _find(pid)
    if p is None:
        return False, "提案不存在"
    if p.get("status") != "pending":
        return False, f"提案当前状态为 {p.get('status')}，不可驳回"
    p["status"] = "rejected"
    p["decided_at"] = time.time()
    _write_all(rows)
    return True, "已驳回"


def rollback(pid: str) -> tuple[bool, str]:
    rows, p = _find(pid)
    if p is None:
        return False, "提案不存在"
    if p.get("status") != "applied":
        return False, "仅已生效的提案可回滚"
    if p["type"] == "prompt_patch":
        ok, detail = prompt_store.rollback(p["target"])
        if not ok:
            return False, detail
    elif p["type"] == "rule_patch":
        overlay = OVERLAYS_DIR / f"{pid}.json"
        if overlay.exists():
            overlay.unlink()
        cache_clear()
        detail = f"已移除 {p['target']} 的规则补丁"
    else:
        return False, "未知提案类型"
    p["status"] = "rolled_back"
    _write_all(rows)
    return True, detail


def _apply(p: dict) -> str:
    if p["type"] == "prompt_patch":
        target = p["target"]
        line = "- " + str(p["change"].get("append", "")).strip()
        current = prompt_store.load(target)
        if line in current:
            return f"规则已存在于 {target}，跳过重复追加"
        prompt_store.save(target, current + "\n" + line, source=f"evolution:{p['id']}")
        return f"已写入 {target} 新版本"
    if p["type"] == "rule_patch":
        OVERLAYS_DIR.mkdir(parents=True, exist_ok=True)
        overlay = {
            "id": p["id"],
            "platform": p["target"],
            "patch": {"bannedWords": {p["change"]["group"]: p["change"]["words"]}},
            "source": "evolution",
            "ts": time.time(),
        }
        (OVERLAYS_DIR / f"{p['id']}.json").write_text(json.dumps(overlay, ensure_ascii=False), encoding="utf-8")
        cache_clear()
        return f"已对 {p['target']} 应用规则补丁（{p['change']['group']} 组 +{len(p['change']['words'])} 词）"
    raise ValueError(f"未知提案类型: {p['type']}")
