"use client";

/**
 * 千岸 QianAn — 工具调用折叠卡片组件
 *
 * 暗色主题（Tailwind CSS + lucide-react），适配千岸 Agent 工具链：
 *   understand_product, submit_plan, draft_listing, revise_copy,
 *   compliance_check, recall_memory, self_reflect, generate_image,
 *   competitor_price_band, gpsr_check, hot_search …
 */

import { useState, useMemo, useEffect } from "react";
import {
  ChevronDown,
  ChevronUp,
  CheckCircle2,
  XCircle,
  Loader2,
  Package,
  ClipboardList,
  FileEdit,
  Sparkles,
  ShieldCheck,
  Brain,
  Lightbulb,
  Image as ImageIcon,
  DollarSign,
  ScanLine,
  TrendingUp,
  Wrench,
  type LucideIcon,
} from "lucide-react";
import type { ToolCall } from "../../lib/chat-types";

/* ============================
   工具元数据映射
   ============================ */

interface ToolMeta {
  label: string;
  icon: LucideIcon;
  color: string; // tailwind text-color class
}

const TOOL_MAP: Record<string, ToolMeta> = {
  understand_product: { label: "产品理解", icon: Package, color: "text-sky-400" },
  submit_plan: { label: "提交规划", icon: ClipboardList, color: "text-violet-400" },
  draft_listing: { label: "撰写文案", icon: FileEdit, color: "text-amber-400" },
  revise_copy: { label: "修订文案", icon: Sparkles, color: "text-pink-400" },
  compliance_check: { label: "合规检查", icon: ShieldCheck, color: "text-emerald-400" },
  recall_memory: { label: "记忆召回", icon: Brain, color: "text-indigo-400" },
  self_reflect: { label: "自我反思", icon: Lightbulb, color: "text-yellow-400" },
  generate_image: { label: "生成图片", icon: ImageIcon, color: "text-rose-400" },
  competitor_price_band: { label: "竞品定价", icon: DollarSign, color: "text-green-400" },
  gpsr_check: { label: "GPSR 检查", icon: ScanLine, color: "text-cyan-400" },
  hot_search: { label: "热搜分析", icon: TrendingUp, color: "text-orange-400" },
};

const DEFAULT_META: ToolMeta = {
  label: "工具调用",
  icon: Wrench,
  color: "text-gray-400",
};

function getToolMeta(name: string): ToolMeta {
  return TOOL_MAP[name.toLowerCase()] || DEFAULT_META;
}

/* ============================
   组件
   ============================ */

interface ToolCallsCollapseProps {
  toolCalls: ToolCall[];
  isStreaming?: boolean;
}

export function ToolCallsCollapse({ toolCalls, isStreaming = false }: ToolCallsCollapseProps) {
  const [isExpanded, setIsExpanded] = useState(false);

  const allCompleted = toolCalls.every((t) => t.status !== "running");
  const hasRunning = toolCalls.some((t) => t.status === "running");
  const hasError = toolCalls.some((t) => t.status === "error");

  // 工具图标汇总
  const summary = useMemo(() => {
    const map = new Map<string, { meta: ToolMeta; count: number }>();
    for (const tc of toolCalls) {
      const key = tc.name.toLowerCase();
      const meta = getToolMeta(tc.name);
      const existing = map.get(key);
      if (existing) existing.count++;
      else map.set(key, { meta, count: 1 });
    }
    return Array.from(map.entries()).map(([key, val]) => ({ key, ...val }));
  }, [toolCalls]);

  // 最新运行中的工具
  const latestRunning = useMemo(() => {
    for (let i = toolCalls.length - 1; i >= 0; i--) {
      if (toolCalls[i].status === "running") return { tool: toolCalls[i], index: i };
    }
    return null;
  }, [toolCalls]);

  // 自动展开逻辑
  useEffect(() => {
    if (toolCalls.length === 1 && hasRunning) {
      setIsExpanded(true);
    } else if (allCompleted && !isStreaming) {
      setIsExpanded(false);
    }
  }, [toolCalls.length, hasRunning, allCompleted, isStreaming]);

  /* ---- 渲染单个工具卡片 ---- */
  const renderToolCard = (tool: ToolCall) => {
    const meta = getToolMeta(tool.name);
    const Icon = meta.icon;
    const isRunning = tool.status === "running";
    const isError = tool.status === "error" || tool.isError;

    const inputStr =
      typeof tool.input === "string"
        ? tool.input
        : (() => {
            try {
              return JSON.stringify(tool.input, null, 2);
            } catch {
              return String(tool.input);
            }
          })();

    return (
      <div
        key={tool.id}
        className="rounded-lg overflow-hidden bg-gray-800 border border-gray-700"
      >
        {/* 标题行 */}
        <div className="flex items-center gap-2 px-3 py-2">
          {isRunning ? (
            <Loader2 size={14} className="animate-spin text-gray-400" />
          ) : isError ? (
            <XCircle size={14} className="text-red-400" />
          ) : (
            <CheckCircle2 size={14} className="text-emerald-400" />
          )}
          <Icon size={15} className={meta.color} />
          <span className="flex-1 text-sm font-medium text-gray-100 truncate">
            {meta.label}
          </span>
          <span className="text-xs text-gray-500 shrink-0">
            {isRunning ? "执行中..." : isError ? "失败" : "完成"}
          </span>
        </div>

        {/* 输入参数 */}
        {inputStr && (
          <div className="px-3 py-2 text-xs font-mono whitespace-pre-wrap break-all max-h-24 overflow-y-auto border-t border-gray-700 bg-gray-900 text-gray-400">
            <span className="text-gray-600">输入: </span>
            {inputStr.length > 300 ? inputStr.slice(0, 300) + "..." : inputStr}
          </div>
        )}

        {/* 结果 */}
        {tool.result && (
          <div className="px-3 py-2 text-xs font-mono whitespace-pre-wrap break-all max-h-32 overflow-y-auto border-t border-gray-700 bg-gray-900 text-gray-400">
            <span className="text-gray-600">{isError ? "错误: " : "结果: "}</span>
            {tool.result.length > 500 ? tool.result.slice(0, 500) + "..." : tool.result}
          </div>
        )}
      </div>
    );
  };

  /* ---- 折叠横条 ---- */
  const renderCollapseBar = () => (
    <div
      className="flex items-center justify-between px-3 py-2 rounded-lg cursor-pointer transition-all hover:bg-gray-800/50 bg-gray-800/30"
      onClick={() => setIsExpanded(!isExpanded)}
    >
      <div className="flex items-center gap-1.5">
        {isExpanded ? (
          <ChevronUp size={15} className="text-gray-500" />
        ) : (
          <ChevronDown size={15} className="text-gray-500" />
        )}
        {hasRunning ? (
          <Loader2 size={15} className="animate-spin text-gray-400" />
        ) : hasError ? (
          <XCircle size={15} className="text-red-400" />
        ) : (
          <CheckCircle2 size={15} className="text-emerald-400" />
        )}
        <span className="text-sm text-gray-200">
          {hasRunning ? "执行中..." : isExpanded ? "收起步骤" : "查看步骤"}
        </span>
        {toolCalls.length > 1 && (
          <span className="text-xs text-gray-500">({toolCalls.length})</span>
        )}
      </div>

      {/* 右侧工具图标汇总 */}
      <div className="flex items-center gap-1">
        {summary.map(({ key, meta, count }) => {
          const Icon = meta.icon;
          return (
            <div
              key={key}
              className="flex items-center gap-0.5 px-1.5 py-0.5 rounded bg-gray-700/50"
              title={`${meta.label} x${count}`}
            >
              <Icon size={12} className={meta.color} />
              {count > 1 && <span className="text-[10px] text-gray-400">{count}</span>}
            </div>
          );
        })}
      </div>
    </div>
  );

  /* ---- 渲染逻辑 ---- */

  // 单个工具
  if (toolCalls.length === 1) {
    const tool = toolCalls[0];
    if (tool.status === "running") {
      return <div className="w-full">{renderToolCard(tool)}</div>;
    }
    return (
      <div className="w-full space-y-2">
        {renderCollapseBar()}
        {isExpanded && <div className="pl-2">{renderToolCard(tool)}</div>}
      </div>
    );
  }

  // 多个工具 — 有运行中且未展开时只显示最新的
  if (hasRunning && !isExpanded) {
    return (
      <div className="w-full space-y-2">
        {latestRunning && latestRunning.index > 0 && (
          <div
            className="flex items-center justify-between gap-1.5 px-3 py-1.5 rounded-lg cursor-pointer hover:bg-gray-800/50 bg-gray-800/30"
            onClick={() => setIsExpanded(true)}
          >
            <div className="flex items-center gap-1.5">
              <ChevronDown size={14} className="text-gray-500" />
              <CheckCircle2 size={14} className="text-emerald-400" />
              <span className="text-xs text-gray-400">
                {latestRunning.index} 个步骤已完成
              </span>
            </div>
            <div className="flex items-center gap-1">
              {summary
                .filter((s) => s.key !== latestRunning.tool.name.toLowerCase())
                .map(({ key, meta }) => {
                  const Icon = meta.icon;
                  return <Icon key={key} size={12} className={meta.color} />;
                })}
            </div>
          </div>
        )}
        {latestRunning && renderToolCard(latestRunning.tool)}
      </div>
    );
  }

  return (
    <div className="w-full space-y-2">
      {renderCollapseBar()}
      {isExpanded && (
        <div className="space-y-2 pl-2">
          {toolCalls.map((tool) => renderToolCard(tool))}
        </div>
      )}
    </div>
  );
}

export default ToolCallsCollapse;
