#!/usr/bin/env python3
"""千岸消融实验（Ablation Study）

逐个关闭 Agentic 组件，度量对输出质量的影响，量化每个能力的独立贡献。

实验设计：
  A (Full)     完整管线（全部组件开启）
  B (-Plan)    去规划：跳过模型规划阶段，用默认计划
  C (-Memory)  去记忆：跳过长期记忆召回与注入
  D (-Heal)    去自愈：跳过合规自愈循环
  E (-Reflect) 去反思：跳过反思阶段（不回写记忆）

评估指标：
  - 合规通过率（compliance_passed）
  - 自愈轮数（revised_count）
  - 合规问题数（error/warn 分别计数）
  - 文案长度分（title + bullets + description 字符总数）
  - 跨平台差异化度（5 平台 title 间的 Jaccard 距离均值）
  - 总耗时（秒）

用法：
  # Mock 模式（快速验证管线正确性，无真实 LLM 调用）
  cd qianan/server && python3 scripts/ablation_study.py

  # 真实模式（调用百炼/TokenDance 网关）
  QIANAN_MOCK=0 BAILIAN_API_KEY=<key> python3 scripts/ablation_study.py

输出：
  - 控制台对比表格
  - JSON 结果文件（供报告生成）
"""
from __future__ import annotations

import asyncio
import hashlib
import json
import os
import sys
import time
from pathlib import Path

# =====================================================================
# 环境设置
# =====================================================================

SERVER_DIR = Path(__file__).resolve().parents[1]
if str(SERVER_DIR) not in sys.path:
    sys.path.insert(0, str(SERVER_DIR))

OUTPUT_DIR = Path(__file__).resolve().parent / "ablation_results"
OUTPUT_DIR.mkdir(exist_ok=True)

# =====================================================================
# 测试商品（固定，保证各组可比）
# =====================================================================

TEST_PRODUCTS = [
    {
        "product_name": "便携保温杯 304不锈钢 500ml",
        "selling_points": "304食品级不锈钢, 双层真空保温12小时, 500ml大容量, 便携轻量, 防漏设计",
        "category": "home_kitchen",
        "platforms": ["amazon", "shopee", "aliexpress", "lazada", "tiktokshop"],
    },
]

# =====================================================================
# 消融配置
# =====================================================================

ABLATION_CONFIGS = [
    ("A_Full", None),  # 完整管线
    ("B_NoPlan", {"disable_plan": True}),
    ("C_NoMemory", {"disable_memory": True}),
    ("D_NoHeal", {"disable_heal": True}),
    ("E_NoReflect", {"disable_reflect": True}),
]

# =====================================================================
# 实验执行
# =====================================================================


def _make_task(product: dict, ablation: dict | None):
    """构造 GenerateRequest + TaskRecord。"""
    from app.schemas import AblationConfig, GenerateRequest, TaskRecord

    abl = AblationConfig(**ablation) if ablation else None
    req = GenerateRequest(**product, ablation=abl)
    task_id = "abl_" + hashlib.md5(
        f"{time.time()}_{json.dumps(ablation or {})}".encode()
    ).hexdigest()[:8]
    return TaskRecord(task_id=task_id, request=req)


def _jaccard_distance(a: str, b: str) -> float:
    """两个字符串的词级 Jaccard 距离（0=完全相同，1=完全不同）。"""
    sa = set(a.lower().split())
    sb = set(b.lower().split())
    if not sa and not sb:
        return 0.0
    return 1.0 - len(sa & sb) / max(1, len(sa | sb))


def _compute_metrics(task, elapsed: float) -> dict:
    """从完成的 TaskRecord 提取评估指标。"""
    listings = task.listings or []
    n = len(listings)

    # 合规
    passed = sum(1 for l in listings if l.compliance_passed)
    errors_total = sum(
        sum(1 for i in l.compliance if i.severity == "error") for l in listings
    )
    warns_total = sum(
        sum(1 for i in l.compliance if i.severity == "warn") for l in listings
    )
    revised_total = sum(l.revised_count for l in listings)

    # 文案长度
    text_lens = []
    titles = []
    for l in listings:
        tl = len(l.title or "")
        bl = sum(len(b) for b in (l.bullets or []))
        dl = len(l.description or "")
        text_lens.append(tl + bl + dl)
        titles.append(l.title or "")

    text_total = sum(text_lens)
    text_avg = text_total / max(1, n)

    # 跨平台差异化度（title 间 Jaccard 距离均值）
    if n >= 2:
        dists = []
        for i in range(n):
            for j in range(i + 1, n):
                dists.append(_jaccard_distance(titles[i], titles[j]))
        diversity = sum(dists) / len(dists) if dists else 0.0
    else:
        diversity = 0.0

    # Agentic 证据
    plan_by = task.plan.decided_by if task.plan else "none"
    plan_strategy = (task.plan.strategy[:80] if task.plan and task.plan.strategy else "")
    memory_count = len(task.memory_recall)
    reflection_count = len(task.reflections)
    trace_count = len(task.trace)

    return {
        "listings_n": n,
        "compliance_pass_rate": round(passed / max(1, n), 4),
        "compliance_passed": passed,
        "errors_total": errors_total,
        "warns_total": warns_total,
        "revised_total": revised_total,
        "text_total_chars": text_total,
        "text_avg_chars": round(text_avg, 1),
        "cross_platform_diversity": round(diversity, 4),
        "elapsed_s": round(elapsed, 2),
        "plan_decided_by": plan_by,
        "plan_strategy": plan_strategy,
        "memory_recall_count": memory_count,
        "reflection_count": reflection_count,
        "trace_count": trace_count,
        "platforms": [
            {
                "platform": l.platform,
                "compliance_passed": l.compliance_passed,
                "revised_count": l.revised_count,
                "errors": sum(1 for i in l.compliance if i.severity == "error"),
                "warns": sum(1 for i in l.compliance if i.severity == "warn"),
                "title_len": len(l.title or ""),
            }
            for l in listings
        ],
    }


async def run_one_config(
    config_name: str,
    ablation: dict | None,
    product: dict,
    client,
) -> dict:
    """跑一组消融配置，返回指标。"""
    from app.orchestrator import run_pipeline

    task = _make_task(product, ablation)
    t0 = time.monotonic()
    try:
        await run_pipeline(task, client)
    except Exception as e:
        task.status = "failed"
        task.error = f"{type(e).__name__}: {e}"
    elapsed = time.monotonic() - t0

    metrics = _compute_metrics(task, elapsed)
    metrics["config"] = config_name
    metrics["ablation"] = ablation
    metrics["status"] = str(task.status)
    if task.error:
        metrics["error"] = task.error[:200]
    return metrics


async def main():
    # 确保环境
    mock_mode = os.getenv("QIANAN_MOCK", "1") == "1"
    if mock_mode:
        os.environ["QIANAN_MOCK"] = "1"
        if not os.environ.get("BAILIAN_API_KEY"):
            os.environ["BAILIAN_API_KEY"] = "ablation-mock-key"

    print("=" * 72)
    print("千岸消融实验 (Ablation Study)")
    print("=" * 72)
    print(f"  模式: {'Mock（确定性脚本）' if mock_mode else '真实（百炼/TokenDance 网关）'}")
    print(f"  测试商品: {len(TEST_PRODUCTS)} 个")
    print(f"  消融配置: {len(ABLATION_CONFIGS)} 组")
    print()

    from app.bailian.client import get_client

    client = get_client()

    all_results = []
    for prod in TEST_PRODUCTS:
        pname = prod["product_name"]
        print(f"--- 商品: {pname} ---")
        for cfg_name, ablation in ABLATION_CONFIGS:
            label = cfg_name
            if ablation:
                label += " (" + ", ".join(f"-{k.replace('disable_', '')}" for k, v in ablation.items() if v) + ")"
            print(f"  运行 {label} ...", end=" ", flush=True)
            result = await run_one_config(cfg_name, ablation, prod, client)
            status_icon = "✓" if result["status"] == "done" else "✗"
            print(
                f"{status_icon} {result['elapsed_s']:.1f}s  "
                f"合规={result['compliance_pass_rate']:.0%}  "
                f"自愈={result['revised_total']}  "
                f"差异度={result['cross_platform_diversity']:.2f}"
            )
            all_results.append(result)

    # =================================================================
    # 输出对比表格
    # =================================================================
    print()
    print("=" * 72)
    print("消融实验结果对比")
    print("=" * 72)

    headers = [
        "配置",
        "合规率",
        "Error",
        "自愈轮",
        "文案均长",
        "差异度",
        "记忆",
        "反思",
        "耗时(s)",
    ]
    rows = []
    for r in all_results:
        rows.append([
            r["config"],
            f"{r['compliance_pass_rate']:.0%}",
            str(r["errors_total"]),
            str(r["revised_total"]),
            str(r["text_avg_chars"]),
            f"{r['cross_platform_diversity']:.2f}",
            str(r["memory_recall_count"]),
            str(r["reflection_count"]),
            f"{r['elapsed_s']:.1f}",
        ])

    col_widths = [max(len(h), max(len(row[i]) for row in rows)) for i, h in enumerate(headers)]
    fmt = "  ".join("{:<" + str(w) + "}" for w in col_widths)
    print(fmt.format(*headers))
    print("-" * (sum(col_widths) + 2 * (len(headers) - 1)))
    for row in rows:
        print(fmt.format(*row))

    # =================================================================
    # 与完整管线的差值
    # =================================================================
    if all_results:
        full = all_results[0]
        print()
        print("--- 相对完整管线的变化 (Delta vs Full) ---")
        for r in all_results[1:]:
            d_pass = (r["compliance_pass_rate"] - full["compliance_pass_rate"]) * 100
            d_err = r["errors_total"] - full["errors_total"]
            d_rev = r["revised_total"] - full["revised_total"]
            d_div = r["cross_platform_diversity"] - full["cross_platform_diversity"]
            d_time = r["elapsed_s"] - full["elapsed_s"]
            print(
                f"  {r['config']:14s}  "
                f"合规{d_pass:+.0f}pp  "
                f"Error{d_err:+d}  "
                f"自愈{d_rev:+d}  "
                f"差异{d_div:+.2f}  "
                f"耗时{d_time:+.1f}s"
            )

    # =================================================================
    # 保存 JSON
    # =================================================================
    out_file = OUTPUT_DIR / f"ablation_{int(time.time())}.json"
    with open(out_file, "w", encoding="utf-8") as f:
        json.dump(all_results, f, ensure_ascii=False, indent=2)
    print(f"\n结果已保存: {out_file}")

    return all_results


if __name__ == "__main__":
    asyncio.run(main())
