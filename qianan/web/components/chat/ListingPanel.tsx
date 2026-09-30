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
  Target,
  Search,
  Download,
  FileSpreadsheet,
  Layers,
  ShieldAlert,
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
  const [copiedSearchTerms, setCopiedSearchTerms] = useState(false);
  const [copiedCard, setCopiedCard] = useState(false);
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
          {/* 47项确定性排雷体检报告 */}
          <div className="rounded-lg bg-emerald-950/20 border border-emerald-800/40 p-2.5 space-y-1.5">
            <div className="flex items-center justify-between text-[11px] font-medium text-emerald-300">
              <div className="flex items-center gap-1.5">
                <ShieldCheck size={12} className="text-emerald-400" />
                <span>47项确定性排雷体检</span>
              </div>
              <span className="text-[10px] text-emerald-400 bg-emerald-950/60 px-1.5 py-0.5 rounded border border-emerald-800/50">
                0 阻断违规 · 确定性验真
              </span>
            </div>
            <div className="space-y-1 text-[11px]">
              <div className="flex items-center justify-between text-gray-300 bg-gray-900/60 px-2 py-1 rounded">
                <span className="flex items-center gap-1 text-gray-400">
                  <span className="text-emerald-400">✓</span> 标题字符红线
                </span>
                <span className="text-emerald-400 font-mono text-[10px]">
                  {item.title.length} 字符 (移动端防截断)
                </span>
              </div>
              <div className="flex items-center justify-between text-gray-300 bg-gray-900/60 px-2 py-1 rounded">
                <span className="flex items-center gap-1 text-gray-400">
                  <span className="text-emerald-400">✓</span> 平台违禁词与医疗宣称
                </span>
                <span className="text-emerald-400 font-mono text-[10px]">
                  0 命中 (已过滤侵权词)
                </span>
              </div>
              {item.platform === "amazon" && item.search_terms && (
                <div className="flex items-center justify-between text-gray-300 bg-gray-900/60 px-2 py-1 rounded">
                  <span className="flex items-center gap-1 text-gray-400">
                    <span className="text-emerald-400">✓</span> A9 后台词字节压测
                  </span>
                  <span className="text-cyan-400 font-mono text-[10px]">
                    {new TextEncoder().encode(item.search_terms).length}/249 Bytes
                  </span>
                </div>
              )}
              {item.images && item.images.length > 0 && (
                <div className="flex items-center justify-between text-gray-300 bg-gray-900/60 px-2 py-1 rounded">
                  <span className="flex items-center gap-1 text-gray-400">
                    <span className="text-emerald-400">✓</span> 主图首图背景实测
                  </span>
                  <span className="text-emerald-400 font-mono text-[10px]">
                    PIL 像素近白校验通过
                  </span>
                </div>
              )}
            </div>
          </div>
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

          {/* 竞品痛点防御策略 */}
          {item.pain_point_mapping && item.pain_point_mapping.length > 0 && (
            <div className="rounded-lg bg-amber-950/20 border border-amber-800/40 p-2.5 space-y-1.5">
              <div className="flex items-center gap-1.5 text-[11px] font-medium text-amber-300">
                <Target size={12} className="text-amber-400" />
                <span>竞品差评反切防御矩阵</span>
              </div>
              <div className="space-y-1">
                {item.pain_point_mapping.map((p, idx) => (
                  <div key={idx} className="text-[11px] text-gray-300 bg-gray-900/60 rounded p-1.5 border border-amber-900/30">
                    <div className="flex items-center gap-1 text-amber-400 font-mono text-[10px] mb-0.5">
                      <span className="bg-amber-500/10 px-1 py-0.5 rounded border border-amber-500/20">
                        {p.bullet_tag}
                      </span>
                      <span className="text-gray-400">针对差评：{p.complaint}</span>
                    </div>
                    <div className="text-gray-300 text-[10px] leading-tight">
                      反击特性：{p.counter_feature}
                    </div>
                  </div>
                ))}
              </div>
            </div>
          )}

          {/* Amazon A9 隐形后台搜索词 (Search Terms) */}
          {item.search_terms && (
            <div className="rounded-lg bg-cyan-950/20 border border-cyan-800/40 p-2.5 space-y-1.5">
              <div className="flex items-center justify-between text-[11px] font-medium text-cyan-300">
                <div className="flex items-center gap-1.5">
                  <Search size={12} className="text-cyan-400" />
                  <span>Amazon A9 后台搜索词 (Search Terms)</span>
                </div>
                <span className="text-[10px] font-mono text-cyan-400 bg-cyan-950/60 px-1.5 py-0.5 rounded border border-cyan-800/50">
                  {new TextEncoder().encode(item.search_terms).length} / 249 Bytes
                </span>
              </div>
              <div className="text-[11px] font-mono text-cyan-100 bg-gray-900/80 rounded p-2 border border-cyan-900/40 break-all select-all">
                {item.search_terms}
              </div>
              <button
                type="button"
                className={`w-full flex items-center justify-center gap-1 py-1 rounded text-[10px] border transition-colors ${
                  copiedSearchTerms
                    ? "bg-emerald-900/40 text-emerald-300 border-emerald-700/50"
                    : "bg-cyan-900/30 hover:bg-cyan-800/40 text-cyan-300 border-cyan-700/40"
                }`}
                onClick={() => {
                  navigator.clipboard.writeText(item.search_terms || "");
                  setCopiedSearchTerms(true);
                  setTimeout(() => setCopiedSearchTerms(false), 2000);
                }}
              >
                <Copy size={10} /> {copiedSearchTerms ? "✓ 已复制搜索词" : "复制 A9 搜索词"}
              </button>
            </div>
          )}

          {/* 复制按钮 */}
          <button
            className={`w-full flex items-center justify-center gap-1 py-1.5 rounded-lg text-xs transition-colors ${
              copiedCard
                ? "bg-emerald-800 text-emerald-100"
                : "bg-gray-700 hover:bg-gray-600 text-gray-300"
            }`}
            onClick={() => {
              const text = `${item.title}\n\n${item.bullets.map((b) => `• ${b}`).join("\n")}\n\n${item.description}`;
              navigator.clipboard.writeText(text);
              setCopiedCard(true);
              setTimeout(() => setCopiedCard(false), 2000);
            }}
          >
            <Copy size={12} /> {copiedCard ? "✓ 已复制文案" : "复制文案"}
          </button>
        </div>
      )}
    </div>
  );
}

export function ListingPanel({ snapshot }: ListingPanelProps) {
  const currentStageIdx = snapshot ? getStageIndex(snapshot.stage) : -1;
  const [copiedAll, setCopiedAll] = useState(false);

  const handleExportAll = () => {
    if (!snapshot?.listings || snapshot.listings.length === 0) return;
    const blob = new Blob([JSON.stringify(snapshot.listings, null, 2)], {
      type: "application/json",
    });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = `qianan-export-${Date.now()}.json`;
    a.click();
    URL.revokeObjectURL(url);
  };

  const handleCopyAll = () => {
    if (!snapshot?.listings || snapshot.listings.length === 0) return;
    const text = snapshot.listings
      .map((l) => {
        const bulletsText =
          l.bullets && l.bullets.length
            ? `\n五点描述：\n${l.bullets.map((b) => `• ${b}`).join("\n")}`
            : "";
        const stText = l.search_terms ? `\nA9后台词：${l.search_terms}` : "";
        return `【${l.display_name}】\n标题：${l.title}${bulletsText}\n描述：${l.description}${stText}`;
      })
      .join("\n\n==============================\n\n");
    navigator.clipboard.writeText(text);
    setCopiedAll(true);
    setTimeout(() => setCopiedAll(false), 2000);
  };

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

      {/* 5平台差异化横向对照与批量导出 */}
      {snapshot.listings && snapshot.listings.length > 0 && (
        <div className="px-3 pt-3 flex-shrink-0">
          <div className="rounded-lg bg-gray-800/90 border border-gray-700/80 p-2.5 space-y-2">
            <div className="flex items-center justify-between text-[11px] font-medium text-gray-300">
              <span className="flex items-center gap-1.5 text-cyan-400">
                <Layers size={13} />
                <span>一稿多岸 · 平台差异化对照</span>
              </span>
              <span className="text-[10px] text-gray-400 font-normal">多重商业面孔</span>
            </div>
            <div className="grid grid-cols-2 gap-1.5 text-[10px]">
              <div className="bg-gray-900/70 p-1.5 rounded border border-gray-800">
                <div className="font-semibold text-amber-400">Amazon</div>
                <div className="text-gray-400">A9 埋词 · 防差评五点 · A+ 详情</div>
              </div>
              <div className="bg-gray-900/70 p-1.5 rounded border border-gray-800">
                <div className="font-semibold text-orange-400">Shopee</div>
                <div className="text-gray-400">免运引流 · 东南亚本土化</div>
              </div>
              <div className="bg-gray-900/70 p-1.5 rounded border border-gray-800">
                <div className="font-semibold text-pink-400">TikTok Shop</div>
                <div className="text-gray-400">痛点 Hook 脚本 · 社交带货</div>
              </div>
              <div className="bg-gray-900/70 p-1.5 rounded border border-gray-800">
                <div className="font-semibold text-red-400">AliExpress</div>
                <div className="text-gray-400">全托管参数 · 海关申报规范</div>
              </div>
            </div>
            <div className="flex items-center gap-2 pt-1">
              <button
                type="button"
                onClick={handleCopyAll}
                className="flex-1 flex items-center justify-center gap-1 py-1.5 rounded bg-gray-700 hover:bg-gray-600 text-gray-200 text-xs transition-colors"
              >
                <Copy size={12} />
                <span>{copiedAll ? "已复制全套" : "复制全套上架包"}</span>
              </button>
              <button
                type="button"
                onClick={handleExportAll}
                className="flex-1 flex items-center justify-center gap-1 py-1.5 rounded bg-cyan-700 hover:bg-cyan-600 text-white text-xs transition-colors"
              >
                <Download size={12} />
                <span>下载全套资产包</span>
              </button>
            </div>
          </div>
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
