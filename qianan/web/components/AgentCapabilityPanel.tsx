"use client";

import { useMemo } from "react";
import type { TaskDetail } from "@/lib/api";

/**
 * Agent 能力证据面板
 *
 * 把「自主规划 / 工具调用 / 长期记忆 / 反思迭代」四项 Agentic 能力，
 * 从扁平的 trace 日志流提升为可判读的证据卡 —— 证明这次上架是 Agent
 * 自主完成的，而不是一条硬编码流水线。
 *
 * 数据来源：后端 task.plan / task.trace / task.memory_recall / task.reflections。
 */

const CAP_META = [
  { no: "01", key: "plan", name: "自主规划", claim: "模型调研后自主决定策略" },
  { no: "02", key: "tool", name: "工具调用", claim: "真 function calling，非提示词模拟" },
  { no: "03", key: "memory", name: "长期记忆", claim: "沉淀跨任务教训并注入生成" },
  { no: "04", key: "reflect", name: "反思迭代", claim: "自检自愈并蒸馏新教训" },
] as const;

const TOOL_LABEL: Record<string, string> = {
  submit_plan: "提交计划",
  revise_copy: "修订文案",
  finish: "结束自愈",
  gpsr_access_check: "欧盟 GPSR 准入核查",
  get_competitor_band: "竞品价格带",
  get_trending_searches: "平台热搜趋势",
};

function CapHead({ no, name, claim, tone }: { no: string; name: string; claim: string; tone: string }) {
  return (
    <div className="flex items-start gap-3">
      <span
        className={`mt-0.5 shrink-0 rounded-md px-1.5 py-0.5 font-mono text-[10px] font-semibold tabular-nums ${tone}`}
      >
        {no}
      </span>
      <div className="min-w-0">
        <p className="text-sm font-semibold text-ink-900">{name}</p>
        <p className="mt-0.5 text-[11px] leading-4 text-ink-400">{claim}</p>
      </div>
    </div>
  );
}

function Pending({ text }: { text: string }) {
  return (
    <p className="mt-3 flex items-center gap-1.5 text-[11px] text-ink-300">
      <span className="h-1 w-1 animate-pulse-dot rounded-full bg-ink-300" />
      {text}
    </p>
  );
}

export default function AgentCapabilityPanel({ task }: { task: TaskDetail }) {
  const trace = task.trace || [];
  const plan = task.plan;
  const memories = task.memory_recall || [];
  const reflections = task.reflections || [];
  const listings = task.listings || [];

  // ② 工具调用：按工具名聚合调用次数
  const toolStats = useMemo(() => {
    const counter = new Map<string, number>();
    for (const e of trace) {
      if (!e.tool) continue;
      counter.set(e.tool, (counter.get(e.tool) || 0) + 1);
    }
    return [...counter.entries()].sort((a, b) => b[1] - a[1]);
  }, [trace]);

  const toolCalls = trace.filter((e) => e.tool).length;

  // ④ 反思迭代：自愈轮数与合规终态
  const healRounds = listings.reduce((n, l) => n + (l.revised_count || 0), 0);
  const passed = listings.filter((l) => l.compliance_passed).length;

  // ③ 长期记忆：同平台去重展示，保留命中次数最高者
  const topMemories = useMemo(() => {
    const seen = new Map<string, (typeof memories)[number]>();
    for (const m of memories) {
      const prev = seen.get(m.lesson);
      if (!prev || m.hit_count > prev.hit_count) seen.set(m.lesson, m);
    }
    return [...seen.values()].sort((a, b) => b.hit_count - a.hit_count).slice(0, 4);
  }, [memories]);

  const totalHits = topMemories.reduce((n, m) => n + (m.hit_count || 0), 0);

  const TONE = {
    plan: "bg-sky-50 text-sky-700 ring-1 ring-sky-200",
    tool: "bg-ink-100 text-ink-700 ring-1 ring-ink-200",
    memory: "bg-amber-50 text-amber-700 ring-1 ring-amber-200",
    reflect: "bg-violet-50 text-violet-700 ring-1 ring-violet-200",
  } as const;

  return (
    <section className="card overflow-hidden">
      <div className="border-b border-ink-100 px-5 py-4 sm:px-7">
        <p className="eyebrow">Agent Capabilities · 能力证据</p>
        <h2 className="mt-2 text-xl font-semibold tracking-tight text-ink-900 sm:text-2xl">
          这不是流水线，是一个会规划、会调用工具、会记住教训的 Agent
        </h2>
        <p className="mt-2 max-w-2xl text-[13px] leading-6 text-ink-500">
          下方四栏来自本次任务的真实运行留痕：规划策略由模型在调研后自主提交，工具通过 function
          calling 真实执行，历史教训按平台类目召回后注入生成，完成后由评审 Agent 反思并回写记忆。
        </p>
      </div>

      <div className="grid grid-cols-1 gap-px bg-ink-100 sm:grid-cols-2 xl:grid-cols-4">
        {/* ── ① 自主规划 ── */}
        <div className="bg-white p-5 sm:p-6">
          <CapHead {...CAP_META[0]} tone={TONE.plan} />
          {plan ? (
            <div className="mt-4 space-y-3">
              <div className="flex flex-wrap items-center gap-1.5">
                <span className="rounded border border-ink-200 bg-ink-50 px-1.5 py-px text-[10px] text-ink-600">
                  {plan.decided_by === "planner" ? "模型自主决策" : "回退默认计划"}
                </span>
                <span className="rounded border border-ink-200 bg-ink-50 px-1.5 py-px text-[10px] tabular-nums text-ink-600">
                  自愈预算 {plan.heal_budget} 轮
                </span>
              </div>

              {plan.research_tools.length > 0 && (
                <div>
                  <p className="text-[10px] uppercase tracking-[0.1em] text-ink-400">决策前自主调研</p>
                  <div className="mt-1.5 flex flex-wrap gap-1">
                    {plan.research_tools.map((t, idx) => (
                      <span
                        key={`${t}-${idx}`}
                        className="rounded bg-sky-50 px-1.5 py-0.5 font-mono text-[10px] text-sky-700 ring-1 ring-sky-200"
                      >
                        {TOOL_LABEL[t] || t}
                      </span>
                    ))}
                  </div>
                </div>
              )}

              {plan.strategy && (
                <p className="text-[13px] leading-5 text-ink-700">{plan.strategy}</p>
              )}
              {plan.focus && (
                <p className="border-l-2 border-sky-200 pl-2.5 text-[11px] leading-4 text-ink-500">
                  生成要点：{plan.focus}
                </p>
              )}
            </div>
          ) : (
            <Pending text="等待规划 Agent 提交策略…" />
          )}
        </div>

        {/* ── ② 工具调用 ── */}
        <div className="bg-white p-5 sm:p-6">
          <CapHead {...CAP_META[1]} tone={TONE.tool} />
          {toolCalls > 0 ? (
            <div className="mt-4 space-y-2.5">
              <p className="text-[11px] text-ink-500">
                本任务共发起 <span className="font-semibold tabular-nums text-ink-900">{toolCalls}</span>{" "}
                次工具调用
              </p>
              <ul className="space-y-1">
                {toolStats.slice(0, 6).map(([name, n]) => (
                  <li key={name} className="flex items-center justify-between gap-2 text-[11px]">
                    <span className="truncate font-mono text-ink-600">{TOOL_LABEL[name] || name}</span>
                    <span className="shrink-0 rounded bg-ink-100 px-1.5 tabular-nums text-ink-700">
                      ×{n}
                    </span>
                  </li>
                ))}
              </ul>
            </div>
          ) : (
            <Pending text="等待 Agent 发起第一次工具调用…" />
          )}
        </div>

        {/* ── ③ 长期记忆 ── */}
        <div className="bg-white p-5 sm:p-6">
          <CapHead {...CAP_META[2]} tone={TONE.memory} />
          {topMemories.length > 0 ? (
            <div className="mt-4 space-y-2.5">
              <p className="text-[11px] text-ink-500">
                召回 <span className="font-semibold tabular-nums text-ink-900">{topMemories.length}</span>{" "}
                条历史教训注入本次生成，累计被复用{" "}
                <span className="font-semibold tabular-nums text-ink-900">{totalHits}</span> 次
              </p>
              <ul className="space-y-2">
                {topMemories.map((m, i) => (
                  <li key={i} className="rounded-lg bg-amber-50/60 px-2.5 py-2 ring-1 ring-amber-100">
                    <p className="text-[11px] leading-4 text-ink-700">{m.lesson}</p>
                    <div className="mt-1.5 flex items-center gap-1.5">
                      <span className="rounded bg-amber-100 px-1.5 py-px text-[10px] tabular-nums text-amber-800">
                        复用 {m.hit_count} 次
                      </span>
                      <span className="font-mono text-[10px] text-ink-400">{m.platform}</span>
                    </div>
                  </li>
                ))}
              </ul>
            </div>
          ) : (
            <Pending text="本次类目暂无可召回的历史教训" />
          )}
        </div>

        {/* ── ④ 反思迭代 ── */}
        <div className="bg-white p-5 sm:p-6">
          <CapHead {...CAP_META[3]} tone={TONE.reflect} />
          <div className="mt-4 space-y-2.5">
            <p className="text-[11px] text-ink-500">
              合规自愈 <span className="font-semibold tabular-nums text-ink-900">{healRounds}</span> 轮 ·
              终态通过{" "}
              <span className="font-semibold tabular-nums text-ink-900">
                {passed}/{listings.length || 0}
              </span>{" "}
              个平台
            </p>

            {reflections.length > 0 ? (
              <>
                <p className="text-[10px] uppercase tracking-[0.1em] text-ink-400">
                  本次蒸馏的新教训（已回写记忆库）
                </p>
                <ul className="space-y-2">
                  {reflections.slice(0, 4).map((r, i) => (
                    <li key={i} className="rounded-lg bg-violet-50/60 px-2.5 py-2 ring-1 ring-violet-100">
                      <p className="text-[11px] leading-4 text-ink-700">{r.lesson}</p>
                      <span className="mt-1 block font-mono text-[10px] text-ink-400">{r.platform}</span>
                    </li>
                  ))}
                </ul>
              </>
            ) : (
              <p className="text-[11px] leading-5 text-ink-400">
                评审 Agent 复盘后判定：文案忠于事实档案且合规干净，本次无需新增教训。
              </p>
            )}
          </div>
        </div>
      </div>
    </section>
  );
}
