"use client";

import { useCallback, useEffect, useState } from "react";
import Link from "next/link";
import Nav from "@/components/Nav";
import {
  AdminStats,
  MetricsOverview,
  PLATFORM_META,
  fetchAdminStats,
  fetchAdminTasks,
  fetchMetricsOverview,
  mockLiveUrl,
} from "@/lib/api";

interface AdminTask {
  task_id: string;
  product_name: string;
  status: string;
  stage: string;
  platforms: string[];
  created_at: number;
  revised_total: number;
  passed_total: number;
  listing_total: number;
  error: string | null;
}

const STATUS_META: Record<string, { label: string; cls: string }> = {
  queued: { label: "排队中", cls: "bg-ink-100 text-ink-500" },
  running: { label: "生成中", cls: "bg-brand-50 text-brand-700" },
  done: { label: "已完成", cls: "bg-green-50 text-green-700" },
  failed: { label: "失败", cls: "bg-red-50 text-red-600" },
};

function fmtTime(ts: number) {
  const d = new Date(ts * 1000);
  return `${d.getMonth() + 1}/${d.getDate()} ${String(d.getHours()).padStart(2, "0")}:${String(
    d.getMinutes()
  ).padStart(2, "0")}`;
}

export default function AdminPage() {
  const [stats, setStats] = useState<AdminStats | null>(null);
  const [tasks, setTasks] = useState<AdminTask[]>([]);
  const [metrics, setMetrics] = useState<MetricsOverview | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  const load = useCallback(async () => {
    setLoading(true);
    setError("");
    try {
      const [s, t, m] = await Promise.all([fetchAdminStats(), fetchAdminTasks(), fetchMetricsOverview()]);
      setStats(s);
      setTasks(t.tasks);
      setMetrics(m);
    } catch (e) {
      setError(`加载失败：${String(e)}`);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  const cards = stats
    ? [
        { label: "Tasks · 总任务", value: stats.tasks.total, cls: "text-ink-900" },
        { label: "Done · 已完成", value: stats.tasks.done, cls: "text-green-700" },
        { label: "Running · 生成中", value: stats.tasks.running + stats.tasks.queued, cls: "text-brand-700" },
        { label: "Failed · 失败", value: stats.tasks.failed, cls: "text-red-600" },
        {
          label: "Pass Rate · 合规通过率",
          value: `${Math.round(stats.compliance.pass_rate * 100)}%`,
          cls: "text-brand-800",
          sub: `${stats.compliance.passed}/${stats.compliance.total} 平台上架包`,
        },
        {
          label: "Self-Heal · 自愈修订",
          value: stats.self_heal.revised_total,
          cls: "text-amber-600",
          sub: "合规拦截后自动修订次数",
        },
        { label: "Images · 生成主图", value: stats.images, cls: "text-ink-900", sub: "全部平台累计" },
        { label: "Packages · 磁盘文件包", value: stats.packages_on_disk, cls: "text-ink-900", sub: "文件管理区可见" },
      ]
    : [];

  const maxPlatform = stats ? Math.max(1, ...Object.values(stats.platforms)) : 1;

  return (
    <main className="pb-24">
      <Nav />

      <div className="mx-auto max-w-6xl px-6">
        {/* ---------- 页头 ---------- */}
        <header className="mt-10 flex animate-fade-up items-end justify-between gap-4">
          <div>
            <p className="eyebrow">Admin · 后台管理</p>
            <h1 className="mt-3 text-3xl font-semibold tracking-tight text-ink-900">后台管理</h1>
            <p className="mt-3 max-w-2xl text-sm leading-6 text-ink-500">
              流水线运行总览：任务状态、平台覆盖、合规与自愈指标（内存任务 + 磁盘文件仓库）
            </p>
          </div>
          <button onClick={load} className="btn-ghost shrink-0">
            刷新
          </button>
        </header>

        {error && (
          <div className="mt-6 rounded-lg bg-red-50 px-4 py-3 font-mono text-xs tracking-[0.04em] text-red-600">
            [ERROR] {error}
          </div>
        )}

        {loading && !stats ? (
          <p className="py-24 text-center font-mono text-xs uppercase tracking-[0.08em] text-ink-400">
            <span className="mr-2 inline-block h-1.5 w-1.5 animate-pulse-dot rounded-full bg-brand-500" />
            Loading · 加载中…
          </p>
        ) : (
          <>
            {/* ---------- 指标卡 ---------- */}
            <div className="mt-8 grid animate-fade-up grid-cols-2 gap-3 sm:grid-cols-4">
              {cards.map((c) => (
                <div key={c.label} className="card px-5 py-4 transition duration-150 hover:shadow-sm">
                  <p className="spec-label">{c.label}</p>
                  <p className={`mt-2 font-mono text-2xl font-medium tabular-nums ${c.cls}`}>{c.value}</p>
                  {c.sub && <p className="mt-1 text-[11px] text-ink-400">{c.sub}</p>}
                </div>
              ))}
            </div>

            <div className="mt-6 grid animate-fade-up grid-cols-1 gap-6 lg:grid-cols-2">
              {/* ---------- 平台覆盖 ---------- */}
              <div className="card p-6 transition duration-150 hover:shadow-sm">
                <p className="eyebrow">Platforms · 平台覆盖</p>
                {stats && Object.keys(stats.platforms).length === 0 ? (
                  <p className="mt-4 border-t border-ink-100 pt-4 text-sm text-ink-400">暂无数据</p>
                ) : (
                  <div className="mt-4 space-y-3 border-t border-ink-100 pt-4">
                    {PLATFORM_META.filter((m) => stats?.platforms[m.key]).map((m) => {
                      const count = stats?.platforms[m.key] || 0;
                      return (
                        <div key={m.key} className="flex items-center gap-3">
                          <span className="w-24 shrink-0 text-xs text-ink-600">{m.name}</span>
                          <div className="h-2.5 flex-1 overflow-hidden rounded-full bg-ink-100">
                            <div
                              className="h-full rounded-full transition-all"
                              style={{ width: `${(count / maxPlatform) * 100}%`, background: m.dot }}
                            />
                          </div>
                          <span className="w-6 shrink-0 text-right font-mono text-xs font-medium tabular-nums text-ink-700">
                            {count}
                          </span>
                        </div>
                      );
                    })}
                  </div>
                )}
              </div>

              {/* ---------- 流水线说明 ---------- */}
              <div className="card p-6 transition duration-150 hover:shadow-sm">
                <p className="eyebrow">Pipeline · 五 Agent 流水线</p>
                <ol className="mt-4 space-y-2.5 border-t border-ink-100 pt-4">
                  {[
                    ["商品理解", "解析商品名与卖点 → 结构化属性 / 关键词"],
                    ["规则引擎", "匹配 5 平台规则库（本地化 / 长度 / 禁用词）"],
                    ["文案 Agent", "按平台 + 语言生成 Listing 与 A+ 详情"],
                    ["视觉 Agent", "以图改图生成白底主图 / 场景图"],
                    ["合规体检", "确定性校验 → error 自动回传修订（自愈）"],
                  ].map(([name, desc], i) => (
                    <li key={name} className="flex items-start gap-3">
                      <span className="mt-0.5 flex h-5 w-5 shrink-0 items-center justify-center rounded-md bg-brand-50 font-mono text-[11px] font-medium tabular-nums text-brand-700">
                        {i + 1}
                      </span>
                      <span>
                        <span className="text-sm font-medium text-ink-700">{name}</span>
                        <span className="ml-2 text-xs text-ink-400">{desc}</span>
                      </span>
                    </li>
                  ))}
                </ol>
              </div>
            </div>

            {/* ---------- 经营数据看板（数据飞轮：上架 → 回流 → 异常 → 进化） ---------- */}
            {metrics && metrics.listings.length > 0 && (
              <div className="card mt-6 animate-fade-up p-6 transition duration-150 hover:shadow-sm">
                <div className="flex flex-wrap items-baseline justify-between gap-2">
                  <p className="eyebrow">Business Data · 经营数据看板</p>
                  <span className="font-mono text-[11px] text-ink-400">
                    mock 模拟流量 · 逻辑时钟加速 · CTR 异常基线 {metrics.baseline.ctr}
                  </span>
                </div>

                {metrics.anomaly_count > 0 && (
                  <div className="mt-4 flex flex-wrap items-center gap-3 rounded-xl border border-red-200 bg-red-50 px-4 py-3">
                    <span className="h-2 w-2 rounded-full bg-red-500 shadow-[0_0_0_3px_rgba(239,68,68,.18)]" />
                    <p className="text-sm font-medium text-red-700">
                      {metrics.anomaly_count} 个商品 CTR 跌破基线，已作为第三证据源注入进化 Agent
                    </p>
                    <Link href="/agent" className="ml-auto text-xs font-medium text-red-600 underline underline-offset-2 hover:text-red-700">
                      查看进化提案 →
                    </Link>
                  </div>
                )}

                <div className="mt-4 overflow-x-auto border-t border-ink-100 pt-4">
                  <table className="w-full text-left text-sm">
                    <thead>
                      <tr className="border-b border-ink-100 text-xs text-ink-400">
                        <th className="pb-2 pr-4 font-medium">SKU</th>
                        <th className="pb-2 pr-4 font-medium">平台</th>
                        <th className="pb-2 pr-4 font-medium">标题质量</th>
                        <th className="pb-2 pr-4 font-medium">曝光</th>
                        <th className="pb-2 pr-4 font-medium">点击</th>
                        <th className="pb-2 pr-4 font-medium">CTR</th>
                        <th className="pb-2 pr-4 font-medium">转化</th>
                        <th className="pb-2 pr-4 font-medium">状态</th>
                        <th className="pb-2 font-medium">溯源</th>
                      </tr>
                    </thead>
                    <tbody>
                      {metrics.listings.map((m) => {
                        const pm = PLATFORM_META.find((x) => x.key === m.platform);
                        return (
                          <tr key={m.sku} className="border-b border-ink-100 last:border-0 transition duration-150 hover:bg-ink-50">
                            <td className="py-2.5 pr-4 font-mono text-xs text-ink-700">{m.sku}</td>
                            <td className="py-2.5 pr-4">
                              <span className="inline-flex items-center gap-1.5 text-xs text-ink-600">
                                <span className="h-1.5 w-1.5 rounded-full" style={{ background: pm?.dot || "#97a6bb" }} />
                                {pm?.name || m.platform}
                              </span>
                            </td>
                            <td className="py-2.5 pr-4 font-mono text-xs tabular-nums text-ink-500">
                              {m.title_quality.toFixed(2)}
                            </td>
                            <td className="py-2.5 pr-4 font-mono text-xs tabular-nums text-ink-700">
                              {m.impressions.toLocaleString()}
                            </td>
                            <td className="py-2.5 pr-4 font-mono text-xs tabular-nums text-ink-700">
                              {m.clicks.toLocaleString()}
                            </td>
                            <td
                              className={`py-2.5 pr-4 font-mono text-xs font-medium tabular-nums ${
                                m.anomaly ? "text-red-600" : "text-green-700"
                              }`}
                            >
                              {(m.ctr * 100).toFixed(2)}%
                            </td>
                            <td className="py-2.5 pr-4 font-mono text-xs tabular-nums text-ink-700">{m.conversions}</td>
                            <td className="py-2.5 pr-4">
                              {m.anomaly ? (
                                <span className="rounded-md bg-red-50 px-2 py-0.5 text-xs font-medium text-red-600">
                                  CTR 异常
                                </span>
                              ) : (
                                <span className="rounded-md bg-green-50 px-2 py-0.5 text-xs font-medium text-green-700">
                                  正常
                                </span>
                              )}
                            </td>
                            <td className="py-2.5 text-xs">
                              <span className="flex gap-2">
                                <a
                                  href={mockLiveUrl(m.listing_id)}
                                  target="_blank"
                                  className="font-medium text-brand-700 hover:text-brand-800"
                                >
                                  live 页 ↗
                                </a>
                                {m.task_id && (
                                  <Link href={`/result?taskId=${m.task_id}`} className="text-ink-400 hover:text-ink-600">
                                    任务
                                  </Link>
                                )}
                              </span>
                            </td>
                          </tr>
                        );
                      })}
                    </tbody>
                  </table>
                </div>
                <p className="mt-3 text-xs text-ink-400">
                  标题质量分由规则计算（长度窗口 / 含品牌 / 关键词丰富度 / 含规格）：质量越低 CTR 系统性越低——异常即进化提案的证据。
                </p>
              </div>
            )}

            {/* ---------- 最近任务 ---------- */}
            <div className="card mt-6 animate-fade-up p-6 transition duration-150 hover:shadow-sm">
              <p className="eyebrow">Recent Tasks · 最近任务</p>
              {tasks.length === 0 ? (
                <p className="mt-4 border-t border-ink-100 pt-4 text-sm text-ink-400">还没有任务，去首页生成第一个商品吧</p>
              ) : (
                <div className="mt-4 overflow-x-auto border-t border-ink-100 pt-4">
                  <table className="w-full text-left text-sm">
                    <thead>
                      <tr className="border-b border-ink-100 text-xs text-ink-400">
                        <th className="pb-2 pr-4 font-medium">商品</th>
                        <th className="pb-2 pr-4 font-medium">状态</th>
                        <th className="pb-2 pr-4 font-medium">平台</th>
                        <th className="pb-2 pr-4 font-medium">合规</th>
                        <th className="pb-2 pr-4 font-medium">自愈</th>
                        <th className="pb-2 font-medium">时间</th>
                      </tr>
                    </thead>
                    <tbody>
                      {tasks.map((t) => {
                        const st = STATUS_META[t.status] || STATUS_META.queued;
                        return (
                          <tr key={t.task_id} className="border-b border-ink-100 last:border-0 transition duration-150 hover:bg-ink-50">
                            <td className="py-2.5 pr-4">
                              <Link
                                href={`/result?taskId=${t.task_id}`}
                                className="font-medium text-ink-800 transition duration-150 hover:text-brand-700"
                              >
                                {t.product_name}
                              </Link>
                              <span className="ml-2 font-mono text-[10px] text-ink-300">{t.task_id}</span>
                            </td>
                            <td className="py-2.5 pr-4">
                              <span className={`rounded-md px-2 py-0.5 text-xs font-medium ${st.cls}`}>
                                {st.label}
                                {t.status === "running" && t.stage ? ` · ${t.stage}` : ""}
                              </span>
                            </td>
                            <td className="py-2.5 pr-4">
                              <span className="flex gap-1">
                                {t.platforms.map((p) => {
                                  const m = PLATFORM_META.find((x) => x.key === p);
                                  return (
                                    <span
                                      key={p}
                                      className="rounded-md bg-ink-100 px-1.5 py-0.5 text-[10px] text-ink-500"
                                    >
                                      {m?.name || p}
                                    </span>
                                  );
                                })}
                              </span>
                            </td>
                            <td className="py-2.5 pr-4 font-mono text-xs tabular-nums text-ink-500">
                              {t.listing_total > 0 ? `${t.passed_total}/${t.listing_total} 通过` : "-"}
                            </td>
                            <td className="py-2.5 pr-4 font-mono text-xs tabular-nums">
                              {t.revised_total > 0 ? (
                                <span className="font-medium text-amber-600">×{t.revised_total}</span>
                              ) : (
                                <span className="text-ink-300">-</span>
                              )}
                            </td>
                            <td className="py-2.5 font-mono text-xs tabular-nums text-ink-400">{fmtTime(t.created_at)}</td>
                          </tr>
                        );
                      })}
                    </tbody>
                  </table>
                </div>
              )}
            </div>
          </>
        )}
      </div>
    </main>
  );
}
