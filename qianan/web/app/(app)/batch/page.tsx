"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import Link from "next/link";
import Nav from "@/components/Nav";
import {
  BatchStatus,
  BatchStatusItem,
  createBatch,
  fetchBatch,
  PLATFORM_META,
  type BatchItem,
} from "@/lib/api";

interface Row extends BatchItem {
  _key: string;
}

const CATEGORIES = [
  { key: "home_kitchen", label: "家居厨房" },
  { key: "electronics", label: "电子数码" },
  { key: "apparel", label: "服饰鞋包" },
];

const SAMPLE: Omit<Row, "_key">[] = [
  {
    product_name: "便携榨汁杯 380ml",
    selling_points: "USB 充电 / 食品级 Tritan 杯体 / 一键启动 / 宿舍健身房便携",
    category: "home_kitchen",
    platforms: [],
  },
  {
    product_name: "磁吸无线充电宝 10000mAh",
    selling_points: "磁吸贴合 / 20W 快充 / 超薄亲肤 / iPhone 同系适配",
    category: "electronics",
    platforms: [],
  },
  {
    product_name: "复古帆布托特包",
    selling_points: "加厚帆布 / 大容量 / 通勤上课 / 可定制刺绣",
    category: "apparel",
    platforms: [],
  },
];

function newKey() {
  return Math.random().toString(36).slice(2, 9);
}

const STATUS_META: Record<string, { label: string; cls: string }> = {
  queued: { label: "排队中", cls: "bg-ink-100 text-ink-500" },
  running: { label: "生成中", cls: "bg-brand-50 text-brand-700" },
  done: { label: "已完成", cls: "bg-emerald-50 text-emerald-600" },
  failed: { label: "失败", cls: "bg-red-50 text-red-600" },
  missing: { label: "丢失", cls: "bg-red-50 text-red-600" },
};

export default function BatchPage() {
  const [rows, setRows] = useState<Row[]>(() =>
    SAMPLE.map((s) => ({ ...s, _key: newKey() }))
  );
  const [platforms, setPlatforms] = useState<string[]>([]);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [batch, setBatch] = useState<BatchStatus | null>(null);
  const [batchId, setBatchId] = useState<string | null>(null);
  const timer = useRef<ReturnType<typeof setInterval> | null>(null);

  const stopPoll = useCallback(() => {
    if (timer.current) {
      clearInterval(timer.current);
      timer.current = null;
    }
  }, []);

  const poll = useCallback(
    async (id: string) => {
      try {
        const st = await fetchBatch(id);
        setBatch(st);
        if (st.done + st.failed >= st.total) stopPoll();
      } catch (e) {
        setError(e instanceof Error ? e.message : "批量进度获取失败");
      }
    },
    [stopPoll]
  );

  useEffect(() => () => stopPoll(), [stopPoll]);

  const updateRow = (key: string, patch: Partial<Row>) =>
    setRows((rs) => rs.map((r) => (r._key === key ? { ...r, ...patch } : r)));

  const addRow = () =>
    setRows((rs) => [
      ...rs,
      { _key: newKey(), product_name: "", selling_points: "", category: "home_kitchen", platforms: [] },
    ]);

  const removeRow = (key: string) =>
    setRows((rs) => (rs.length > 1 ? rs.filter((r) => r._key !== key) : rs));

  const reset = () => {
    stopPoll();
    setBatch(null);
    setBatchId(null);
    setError(null);
    setRows(SAMPLE.map((s) => ({ ...s, _key: newKey() })));
  };

  const submit = async () => {
    setError(null);
    const items: BatchItem[] = rows
      .map(({ product_name, selling_points, category, image_url, image_base64, platforms: _p }) => ({
        product_name,
        selling_points,
        category,
        image_url,
        image_base64,
        platforms: [] as string[],
      }))
      .filter((i) => i.product_name.trim() || i.selling_points.trim());
    if (!items.length) {
      setError("请至少填写一个商品的名称或卖点");
      return;
    }
    setSubmitting(true);
    try {
      const res = await createBatch(items, platforms.length ? platforms : undefined);
      setBatchId(res.batch_id);
      await poll(res.batch_id);
      timer.current = setInterval(() => poll(res.batch_id), 2500);
    } catch (e) {
      setError(e instanceof Error ? e.message : "批量提交失败");
    } finally {
      setSubmitting(false);
    }
  };

  const allPlatforms = platforms.length ? platforms : PLATFORM_META.map((p) => p.key);

  return (
    <main className="min-h-screen bg-ink-50/40">
      <Nav />
      <div className="mx-auto max-w-6xl px-6 py-8">
        <header className="mb-6">
          <h1 className="text-[22px] font-semibold tracking-tight text-ink-900">批量上新</h1>
          <p className="mt-1 text-sm text-ink-500">
            一次提交多个商品，逐一对齐 5 个平台生成合规 Listing 并上架 —— 赛事场景一「批量完成 Listing 撰写与后台上架」。
          </p>
        </header>

        {error && (
          <div
            role="alert"
            className="mb-4 rounded-lg border border-red-200 bg-red-50 px-3 py-2 text-sm text-red-600"
          >
            {error}
          </div>
        )}

        {!batch ? (
          <>
            {/* 平台范围 */}
            <section className="mb-5 rounded-xl border border-ink-100 bg-white p-4">
              <span className="spec-label mb-2 block">上架平台范围（留空 = 全部 5 平台）</span>
              <div className="flex flex-wrap gap-2">
                {PLATFORM_META.map((p) => {
                  const on = allPlatforms.includes(p.key);
                  return (
                    <button
                      key={p.key}
                      onClick={() =>
                        setPlatforms((ps) =>
                          ps.includes(p.key) ? ps.filter((x) => x !== p.key) : [...ps, p.key]
                        )
                      }
                      className={`flex items-center gap-1.5 rounded-full border px-3 py-1 text-[12.5px] transition ${
                        on
                          ? "border-brand-500 bg-brand-50 text-brand-700"
                          : "border-ink-200 bg-white text-ink-500 hover:bg-ink-50"
                      }`}
                    >
                      <span className="h-2 w-2 rounded-full" style={{ background: p.dot }} />
                      {p.name}
                    </button>
                  );
                })}
              </div>
            </section>

            {/* 商品清单 */}
            <section className="rounded-xl border border-ink-100 bg-white">
              <div className="flex items-center justify-between border-b border-ink-100 px-4 py-3">
                <span className="text-sm font-medium text-ink-800">
                  商品清单 <span className="font-mono text-ink-400">（{rows.length} 个）</span>
                </span>
                <button
                  onClick={addRow}
                  className="rounded-md border border-ink-200 px-2.5 py-1 text-[12.5px] text-ink-600 transition hover:bg-ink-50"
                >
                  + 添加商品
                </button>
              </div>

              <div className="divide-y divide-ink-100">
                {rows.map((r, idx) => (
                  <div key={r._key} className="grid grid-cols-1 gap-3 p-4 md:grid-cols-[28px_1fr_2fr_140px_32px]">
                    <span className="hidden font-mono text-xs text-ink-400 md:block md:pt-2">
                      {idx + 1}
                    </span>
                    <input
                      value={r.product_name}
                      onChange={(e) => updateRow(r._key, { product_name: e.target.value })}
                      placeholder="商品名称"
                      className="rounded-lg border border-ink-200 bg-white px-2.5 py-1.5 text-sm text-ink-800 outline-none focus:border-brand-500 focus:ring-2 focus:ring-brand-100"
                    />
                    <textarea
                      value={r.selling_points}
                      onChange={(e) => updateRow(r._key, { selling_points: e.target.value })}
                      placeholder="中文卖点，用 / 或逗号分隔"
                      rows={2}
                      className="resize-none rounded-lg border border-ink-200 bg-white px-2.5 py-1.5 text-sm text-ink-800 outline-none focus:border-brand-500 focus:ring-2 focus:ring-brand-100"
                    />
                    <select
                      value={r.category}
                      onChange={(e) => updateRow(r._key, { category: e.target.value })}
                      className="rounded-lg border border-ink-200 bg-white px-2 py-1.5 text-sm text-ink-800 outline-none focus:border-brand-500"
                    >
                      {CATEGORIES.map((c) => (
                        <option key={c.key} value={c.key}>
                          {c.label}
                        </option>
                      ))}
                    </select>
                    <button
                      onClick={() => removeRow(r._key)}
                      disabled={rows.length <= 1}
                      className="flex items-center justify-center rounded-md border border-ink-200 text-ink-400 transition hover:bg-ink-50 disabled:opacity-30"
                      title="删除"
                    >
                      ×
                    </button>
                  </div>
                ))}
              </div>
            </section>

            <div className="mt-5 flex items-center gap-3">
              <button
                onClick={submit}
                disabled={submitting}
                className="rounded-lg bg-brand-800 px-5 py-2.5 text-sm font-medium text-white shadow-sm transition hover:bg-brand-700 disabled:opacity-60"
              >
                {submitting ? "提交中…" : `批量生成 ${rows.length} 个 Listing`}
              </button>
              <span className="text-xs text-ink-400">
                每个商品将独立走完规划 / 合规 / 自愈 / 反思 / 上架全流水线
              </span>
            </div>
          </>
        ) : (
          <BatchResultView batch={batch} batchId={batchId} onReset={reset} />
        )}
      </div>
    </main>
  );
}

function BatchResultView({
  batch,
  batchId,
  onReset,
}: {
  batch: BatchStatus;
  batchId: string | null;
  onReset: () => void;
}) {
  const pct = batch.total ? Math.round(((batch.done + batch.failed) / batch.total) * 100) : 0;
  return (
    <section className="rounded-xl border border-ink-100 bg-white p-5">
      <div className="mb-4 flex flex-wrap items-center justify-between gap-3">
        <div>
          <h2 className="text-base font-semibold text-ink-900">批量进度</h2>
          {batchId && <p className="mt-0.5 font-mono text-[11px] text-ink-400">{batchId}</p>}
        </div>
        <button
          onClick={onReset}
          className="rounded-md border border-ink-200 px-3 py-1.5 text-[12.5px] text-ink-600 transition hover:bg-ink-50"
        >
          新建批量
        </button>
      </div>

      <div className="mb-4 flex items-center gap-3">
        <div className="h-2 flex-1 overflow-hidden rounded-full bg-ink-100">
          <div className="h-full bg-brand-600 transition-all duration-500" style={{ width: `${pct}%` }} />
        </div>
        <span className="font-mono text-xs text-ink-500">
          {batch.done + batch.failed}/{batch.total}
        </span>
      </div>

      <div className="grid grid-cols-1 gap-3 md:grid-cols-2 lg:grid-cols-3">
        {batch.items.map((it: BatchStatusItem) => {
          const meta = STATUS_META[it.status] || STATUS_META.queued;
          return (
            <div key={it.task_id} className="rounded-lg border border-ink-100 bg-ink-50/40 p-3">
              <div className="flex items-start justify-between gap-2">
                <span className="truncate text-sm font-medium text-ink-900">
                  {it.product_name || "（未命名商品）"}
                </span>
                <span className={`shrink-0 rounded px-1.5 py-0.5 font-mono text-[10px] font-medium ${meta.cls}`}>
                  {meta.label}
                </span>
              </div>
              <p className="mt-1 font-mono text-[10px] text-ink-400">
                {it.task_id.slice(0, 8)} · {it.stage || "—"}
              </p>
              <div className="mt-2 flex flex-wrap gap-1">
                {it.platforms.map((p) => {
                  const m = PLATFORM_META.find((x) => x.key === p);
                  return (
                    <span
                      key={p}
                      className="flex items-center gap-1 rounded px-1.5 py-0.5 text-[10px] text-ink-500"
                      style={{ background: `${m?.dot}1a` }}
                    >
                      <span className="h-1.5 w-1.5 rounded-full" style={{ background: m?.dot }} />
                      {m?.name || p}
                    </span>
                  );
                })}
              </div>
              {it.status === "done" && (
                <Link
                  href={`/result?taskId=${it.task_id}`}
                  className="mt-3 inline-block rounded-md bg-brand-800 px-3 py-1.5 text-[12px] font-medium text-white transition hover:bg-brand-700"
                >
                  查看 Listing →
                </Link>
              )}
              {it.status === "running" && (
                <div className="mt-3 h-1 w-full overflow-hidden rounded-full bg-ink-100">
                  <div
                    className="h-full bg-brand-500 transition-all"
                    style={{ width: `${Math.max(8, it.progress * 100)}%` }}
                  />
                </div>
              )}
            </div>
          );
        })}
      </div>
    </section>
  );
}
