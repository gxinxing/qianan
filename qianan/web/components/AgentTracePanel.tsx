"use client";

import { useEffect, useRef } from "react";
import type { TraceEvent } from "@/lib/types";

const PHASE_LABEL: Record<string, string> = {
  plan: "规划",
  build: "生成",
  heal: "自愈",
  reflect: "反思",
  evolve: "进化",
};

const PHASE_STYLE: Record<string, string> = {
  plan: "bg-sky-500/15 text-sky-300 border-sky-400/30",
  build: "bg-brand-400/15 text-brand-200 border-brand-300/30",
  heal: "bg-amber-500/15 text-amber-300 border-amber-400/30",
  reflect: "bg-violet-500/15 text-violet-300 border-violet-400/30",
  evolve: "bg-teal-500/15 text-teal-300 border-teal-400/30",
};

const PHASE_STYLE_LIGHT: Record<string, string> = {
  plan: "bg-sky-50 text-sky-700 border-sky-200",
  build: "bg-brand-50 text-brand-700 border-brand-200",
  heal: "bg-amber-50 text-amber-700 border-amber-200",
  reflect: "bg-violet-50 text-violet-700 border-violet-200",
  evolve: "bg-teal-50 text-teal-700 border-teal-200",
};

function clock(ts: number): string {
  try {
    return new Date(ts * 1000).toLocaleTimeString("zh-CN", { hour12: false });
  } catch {
    return "--:--:--";
  }
}

/**
 * Agent 实时动态面板：把后端 task.trace（规划/生成/自愈/反思每一步工具调用留痕）
 * 以终端日志流的形式实时呈现 —— 结果页的「agent 工作台」感知来源。
 */
export default function AgentTracePanel({
  events,
  running = false,
  variant = "dark",
}: {
  events: TraceEvent[];
  running?: boolean;
  variant?: "dark" | "light";
}) {
  const boxRef = useRef<HTMLDivElement>(null);
  const count = events.length;
  const errCount = events.filter((e) => e.status === "error").length;
  const healCount = events.filter((e) => e.phase === "heal").length;

  // 新事件到达时自动滚到底部（日志流体验）
  useEffect(() => {
    const el = boxRef.current;
    if (el) el.scrollTop = el.scrollHeight;
  }, [count]);

  const dark = variant === "dark";

  return (
    <div
      className={`overflow-hidden rounded-xl border font-mono ${
        dark ? "border-white/12 bg-black/30 backdrop-blur-sm" : "card"
      }`}
    >
      {/* 头部：Live 指示 */}
      <div
        className={`flex items-center justify-between border-b px-4 py-3 ${
          dark ? "border-white/10" : "border-ink-100"
        }`}
      >
        <div className="flex items-center gap-2">
          {running ? (
            <span className={`h-1.5 w-1.5 animate-pulse-dot rounded-full ${dark ? "bg-green-400" : "bg-brand-600"}`} />
          ) : (
            <span className={`h-1.5 w-1.5 rounded-full ${dark ? "bg-green-400/60" : "bg-green-500"}`} />
          )}
          <span
            className={`text-[11px] uppercase tracking-[0.12em] ${
              dark ? "text-brand-200" : "text-ink-600"
            }`}
          >
            Agent {running ? "Live" : "Trace"}
          </span>
        </div>
        <span className={`text-[10px] tabular-nums ${dark ? "text-brand-200/50" : "text-ink-400"}`}>
          {count} 步{healCount ? ` · 自愈 ${healCount}` : ""}{errCount ? ` · 异常 ${errCount}` : ""}
        </span>
      </div>

      {/* 日志流 */}
      <div
        ref={boxRef}
        className={`max-h-[420px] space-y-0 overflow-y-auto px-4 py-3 xl:max-h-[560px] ${
          dark ? "" : ""
        }`}
      >
        {count === 0 && (
          <p className={`py-6 text-center text-[11px] ${dark ? "text-brand-200/40" : "text-ink-300"}`}>
            {running ? "agent 正在唤醒，等待第一步…" : "暂无轨迹"}
          </p>
        )}
        {events.map((e, i) => {
          const phaseLabel = PHASE_LABEL[e.phase] || e.phase;
          const phaseStyle = (dark ? PHASE_STYLE : PHASE_STYLE_LIGHT)[e.phase] ||
            (dark
              ? "bg-white/10 text-brand-100 border-white/20"
              : "bg-ink-50 text-ink-600 border-ink-200");
          const isError = e.status === "error";
          const isFallback = e.status === "fallback";
          return (
            <div
              key={`${e.ts}-${i}`}
              className={`border-l-2 py-1.5 pl-3 ${
                dark ? "border-white/10" : "border-ink-100"
              } ${isError ? "!border-red-400" : isFallback ? "!border-amber-400" : ""}`}
            >
              <div className="flex flex-wrap items-center gap-x-2 gap-y-1">
                <span className={`text-[10px] tabular-nums ${dark ? "text-brand-200/40" : "text-ink-300"}`}>
                  {clock(e.ts)}
                </span>
                <span className={`rounded border px-1.5 py-px text-[10px] leading-4 ${phaseStyle}`}>
                  {phaseLabel}
                </span>
                <span className={`text-[11px] font-medium ${dark ? "text-white" : "text-ink-800"}`}>
                  {e.tool}
                </span>
                {isError && <span className="text-[10px] text-red-400">error</span>}
                {isFallback && <span className="text-[10px] text-amber-400">fallback</span>}
              </div>
              {(e.args_summary || e.result_summary) && (
                <p className={`mt-0.5 line-clamp-2 text-[11px] leading-4 ${dark ? "text-brand-100/60" : "text-ink-500"}`}>
                  {e.args_summary && <span className="opacity-60">▸ {e.args_summary}</span>}
                  {e.args_summary && e.result_summary && <span className="opacity-40"> → </span>}
                  {e.result_summary}
                </p>
              )}
            </div>
          );
        })}
      </div>

      {/* 底部状态行 */}
      <div
        className={`border-t px-4 py-2 text-[10px] uppercase tracking-[0.1em] ${
          dark ? "border-white/10 text-brand-200/40" : "border-ink-100 text-ink-400"
        }`}
      >
        {running ? (
          <span className="flex items-center gap-1.5">
            <span className={`h-1 w-1 animate-pulse-dot rounded-full ${dark ? "bg-green-400" : "bg-brand-600"}`} />
            Working · 每 1.5s 刷新
          </span>
        ) : (
          "Run completed"
        )}
      </div>
    </div>
  );
}
