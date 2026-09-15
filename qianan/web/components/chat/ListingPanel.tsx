"use client";

/**
 * 千岸 QianAn — 右侧产物面板
 *
 * 展示 Agent pipeline 进度 + 多平台 listing 产物卡片。
 * 由 useChat 的 onListingEvent 回调驱动的 ListingSnapshot 数据。
 */

import {
  Package,
  ClipboardList,
  FileEdit,
  Sparkles,
  ShieldCheck,
  Brain,
  Lightbulb,
  CheckCircle2,
  Loader2,
  Copy,
  ChevronDown,
  ChevronUp,
} from "lucide-react";
import { useState, useMemo } from "react";
import type { ListingSnapshot, ListingItem } from "../../lib/chat-types";

interface ListingPanelProps {
  snapshot: ListingSnapshot | null;
}

/* ---- pipeline 阶段定义 ---- */
const STAGES = [
  { key: "plan", label: "规划", icon: ClipboardList, color: "text-violet-400" },
  { key: "build", label: "生成", icon: FileEdit, color: "text-amber-400" },
  { key: "heal", label: "自愈", icon: ShieldCheck, color: "text-emerald-400" },
  { key: "reflect", label: "反思", icon: Lightbulb, color: "text-yellow-400" },
  { key: "evolve", label: "进化", icon: Brain, color: "text-indigo-400" },
];

function getStageIndex(stage: string): number {
  const idx = STAGES.findIndex((s) => s.key === stage);
  return idx >= 0 ? idx : -1;
}

/* ---- 单个平台产物卡片 ---- */
function ListingCard({ item }: { item: ListingItem }) {
  const [expanded, setExpanded] = useState(false);
  const complianceColor = item.compliance_passed
    ? "text-emerald-400"
    : "text-red-400";
  const complianceBg = item.compliance_passed
    ? "bg-emerald-500/10 border-emerald-500/30"
    : "bg-red-500/10 border-red-500/30";

  return (
    <div className="rounded-xl bg-gray-800 border border-gray-700 overflow-hidden">
      {/* 头部 */}
      <div className="flex items-center justify-between px-3 py-2 border-b border-gray-700">
        <div className="flex items-center gap-2">
          <Package size={14} className="text-cyan-400" />
          <span className="text-sm font-medium text-gray-100">{item.display_name}</span>
          {item.revised_count > 0 && (
            <span className="text-[10px] px-1.5 py-0.5 rounded bg-amber-500/20 text-amber-400">
              修订 ×{item.revised_count}
            </span>
          )}
        </div>
        <div className={`flex items-center gap-1 text-xs ${complianceColor}`}>
          <ShieldCheck size={12} />
          {item.compliance_passed ? "合规" : "不合规"}
        </div>
      </div>

      {/* 标题 */}
      <div className="px-3 py-2 border-b border-gray-700/50">
        <div className="text-[10px] text-gray-500 mb-0.5">标题</div>
        <div className="text-sm text-gray-200 line-clamp-2">{item.title}</div>
      </div>

      {/* 展开切换 */}
      <button
        className="w-full flex items-center justify-center gap-1 py-1.5 text-xs text-gray-500 hover:text-gray-300 hover:bg-gray-700/30 transition-colors"
        onClick={() => setExpanded(!expanded)}
      >
        {expanded ? <ChevronUp size={12} /> : <ChevronDown size={12} />}
        {expanded ? "收起" : "展开详情"}
      </button>

      {expanded && (
        <div className="px-3 pb-3 space-y-3">
          {/* 卖点 */}
          {item.bullets && item.bullets.length > 0 && (
            <div>
              <div className="text-[10px] text-gray-500 mb-1">核心卖点</div>
              <ul className="space-y-1">
                {item.bullets.map((b, i) => (
                  <li
                    key={i}
                    className="text-xs text-gray-300 flex items-start gap-1.5"
                  >
                    <span className="text-cyan-500 mt-0.5">•</span>
                    <span className="flex-1">{b}</span>
                  </li>
                ))}
              </ul>
            </div>
          )}

          {/* 描述 */}
          {item.description && (
            <div>
              <div className="text-[10px] text-gray-500 mb-1">描述</div>
              <div className="text-xs text-gray-400 whitespace-pre-wrap max-h-40 overflow-y-auto">
                {item.description}
              </div>
            </div>
          )}

          {/* 合规详情 */}
          {(item.compliance_errors > 0 || item.compliance_warns > 0) && (
            <div className={`rounded-lg border px-2 py-1.5 text-xs ${complianceBg}`}>
              <div className={complianceColor}>
                {item.compliance_errors > 0 && `${item.compliance_errors} 项错误`}
                {item.compliance_errors > 0 && item.compliance_warns > 0 && " · "}
                {item.compliance_warns > 0 && `${item.compliance_warns} 项警告`}
              </div>
            </div>
          )}

          {/* 复制按钮 */}
          <button
            className="w-full flex items-center justify-center gap-1 py-1.5 rounded-lg bg-gray-700 hover:bg-gray-600 text-gray-300 text-xs transition-colors"
            onClick={() => {
              const text = `${item.title}\n\n${item.bullets.map((b) => `• ${b}`).join("\n")}\n\n${item.description}`;
              navigator.clipboard.writeText(text);
            }}
          >
            <Copy size={12} /> 复制文案
          </button>
        </div>
      )}
    </div>
  );
}

export function ListingPanel({ snapshot }: ListingPanelProps) {
  const currentStageIdx = snapshot ? getStageIndex(snapshot.stage) : -1;

  const planSummary = useMemo(() => {
    if (!snapshot?.plan) return null;
    const p = snapshot.plan;
    return p;
  }, [snapshot]);

  if (!snapshot) {
    return (
      <aside className="flex flex-col w-[420px] flex-shrink-0 h-full bg-gray-900 border-l border-gray-800">
        <div className="flex flex-col items-center justify-center h-full text-gray-600 gap-3">
          <Package size={40} className="opacity-20" />
          <p className="text-sm text-center px-8">
            Agent 产物将在此处实时展示
            <br />
            <span className="text-xs">包括多平台 Listing、合规状态、Pipeline 进度</span>
          </p>
        </div>
      </aside>
    );
  }

  return (
    <aside className="flex flex-col w-[420px] flex-shrink-0 h-full bg-gray-900 border-l border-gray-800">
      {/* 头部：状态 */}
      <div className="px-4 py-3 border-b border-gray-800 flex-shrink-0">
        <div className="flex items-center justify-between mb-2">
          <span className="text-sm font-semibold text-gray-200">Agent 产物</span>
          <span
            className={`text-xs px-2 py-0.5 rounded-full ${
              snapshot.status === "done"
                ? "bg-emerald-500/20 text-emerald-400"
                : "bg-cyan-500/20 text-cyan-400"
            }`}
          >
            {snapshot.status === "done" ? "完成" : snapshot.stage}
          </span>
        </div>

        {/* Pipeline 进度条 */}
        <div className="flex items-center gap-1">
          {STAGES.map((stage, idx) => {
            const Icon = stage.icon;
            const isDone = idx < currentStageIdx;
            const isCurrent = idx === currentStageIdx;
            return (
              <div key={stage.key} className="flex items-center flex-1">
                <div
                  className={`flex items-center gap-1 px-1.5 py-1 rounded text-[10px] transition-all ${
                    isCurrent
                      ? "bg-cyan-500/20 text-cyan-400"
                      : isDone
                        ? "text-gray-500"
                        : "text-gray-700"
                  }`}
                >
                  {isCurrent ? (
                    <Loader2 size={11} className="animate-spin" />
                  ) : isDone ? (
                    <CheckCircle2 size={11} />
                  ) : (
                    <Icon size={11} />
                  )}
                  <span>{stage.label}</span>
                </div>
                {idx < STAGES.length - 1 && (
                  <div
                    className={`h-px flex-1 ${isDone ? "bg-gray-600" : "bg-gray-800"}`}
                  />
                )}
              </div>
            );
          })}
        </div>
      </div>

      {/* Plan 摘要 */}
      {planSummary && (
        <div className="px-4 py-2.5 border-b border-gray-800 flex-shrink-0">
          <div className="text-[10px] text-gray-500 mb-1">策略规划</div>
          <div className="text-xs text-gray-300 line-clamp-2">{planSummary.strategy}</div>
          {planSummary.focus && (
            <div className="text-[10px] text-gray-500 mt-1">重点: {planSummary.focus}</div>
          )}
        </div>
      )}

      {/* Listing 列表 */}
      <div className="flex-1 overflow-y-auto px-3 py-3 space-y-3">
        {snapshot.listings && snapshot.listings.length > 0 ? (
          snapshot.listings.map((item, i) => <ListingCard key={i} item={item} />)
        ) : (
          <div className="flex items-center justify-center py-8 text-gray-600 text-xs">
            {snapshot.status === "done" ? "无产物数据" : "生成中..."}
          </div>
        )}
      </div>
    </aside>
  );
}

export default ListingPanel;
