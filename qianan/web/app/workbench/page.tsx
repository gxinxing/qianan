"use client";

import { useCallback, useEffect, useState } from "react";
import Link from "next/link";
import Nav from "@/components/Nav";
import {
  AdminStats,
  EconomicsResult,
  PackageInfo,
  PLATFORM_META,
  PlatformEconomics,
  createTask,
  fetchAdminStats,
  fetchAdminTasks,
  fetchFiles,
  runEconomics,
} from "@/lib/api";
import { SAMPLES } from "@/lib/samples";

interface RunningTask {
  task_id: string;
  product_name: string;
  status: string;
  stage: string;
  platforms: string[];
  created_at: number;
}

const ECO_SEGMENTS = [
  { key: "purchase", label: "采购", color: "#97a6bb" },
  { key: "first_mile", label: "头程", color: "#cdd5e0" },
  { key: "last_mile", label: "尾程", color: "#818cf8" },
  { key: "storage", label: "仓储", color: "#7dd3fc" },
  { key: "return_loss", label: "退货", color: "#fca5a5" },
  { key: "commission", label: "佣金", color: "#fdba74" },
  { key: "ad", label: "广告", color: "#f0abfc" },
  { key: "vat", label: "VAT", color: "#ddd6fe" },
  { key: "profit", label: "净利", color: "#34d399" },
] as const;

const VERDICT_META: Record<string, { label: string; cls: string }> = {
  green: { label: "可上", cls: "bg-emerald-50 text-emerald-600" },
  yellow: { label: "需溢价", cls: "bg-amber-50 text-amber-600" },
  red: { label: "建议放弃", cls: "bg-red-50 text-red-600" },
};

function EcoField({
  label,
  value,
  onChange,
  suffix,
}: {
  label: string;
  value: string;
  onChange: (v: string) => void;
  suffix?: string;
}) {
  return (
    <label className="block">
      <span className="spec-label mb-1 block">{label}</span>
      <span className="flex items-center rounded-lg border border-ink-200 bg-white shadow-xs transition duration-150 focus-within:border-brand-500 focus-within:ring-2 focus-within:ring-brand-100">
        <input
          value={value}
          onChange={(e) => onChange(e.target.value)}
          inputMode="decimal"
          className="w-full rounded-l-lg bg-transparent px-2.5 py-1.5 font-mono text-xs text-ink-800 outline-none"
        />
        {suffix && <span className="pr-2 font-mono text-[10px] text-ink-400">{suffix}</span>}
      </span>
    </label>
  );
}

function EcoRow({ p }: { p: PlatformEconomics }) {
  const verdict = VERDICT_META[p.verdict] || VERDICT_META.green;
  return (
    <div className="px-1 py-3">
      <div className="flex flex-wrap items-center gap-2">
        <span
          className="h-1.5 w-1.5 rounded-full"
          style={{ background: PLATFORM_META.find((m) => m.key === p.platform)?.dot || "#999" }}
        />
        <span className="text-sm font-medium text-ink-900">{p.display_name}</span>
        <span className={`rounded px-1.5 py-0.5 font-mono text-[10px] font-medium ${verdict.cls}`}>
          {verdict.label}
        </span>
        <span className="ml-auto font-mono text-xs text-ink-500">
          建议 <b className="font-semibold text-ink-900">${p.suggested_price.toFixed(2)}</b>
          <span className="text-ink-400">
            {" "}
            · 保本 ${p.break_even_price.toFixed(2)} · 净利率 {(p.margin * 100).toFixed(1)}%
          </span>
        </span>
      </div>
      <div className="mt-2 flex h-1.5 w-full overflow-hidden rounded-full bg-ink-100">
        {ECO_SEGMENTS.map((s) => {
          const v = p[s.key as keyof PlatformEconomics] as number;
          if (!v) return null;
          return (
            <span key={s.key} style={{ width: `${(v / p.suggested_price) * 100}%`, background: s.color }} />
          );
        })}
      </div>
      <p className="mt-1.5 text-[11px] leading-5 text-ink-400">
        {p.verdict_reason}
        {p.bep_units ? ` · 盈亏平衡 ${p.bep_units} 件` : ""}
      </p>
    </div>
  );
}

function fmtTime(ts: number) {
  const d = new Date(ts * 1000);
  return `${d.getMonth() + 1}/${d.getDate()} ${String(d.getHours()).padStart(2, "0")}:${String(
    d.getMinutes()
  ).padStart(2, "0")}`;
}

function fmtSize(bytes: number) {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / 1024 / 1024).toFixed(2)} MB`;
}

const STAGES = [
  { key: "pre", label: "上架前", desc: "选品 · 编辑" },
  { key: "on", label: "上架中", desc: "生成进度 · 平台状态" },
  { key: "post", label: "上架后", desc: "文件 · 导出 · 复盘" },
];

const PIPELINE_PHASES = ["plan", "build", "heal", "reflect", "evolve"];

export default function WorkbenchPage() {
  const [productName, setProductName] = useState("");
  const [sellingPoints, setSellingPoints] = useState("");
  const [category, setCategory] = useState("home_kitchen");
  const [platforms, setPlatforms] = useState<string[]>(PLATFORM_META.map((p) => p.key));
  const [submitting, setSubmitting] = useState(false);

  const [running, setRunning] = useState<RunningTask[]>([]);
  const [packages, setPackages] = useState<PackageInfo[]>([]);
  const [stats, setStats] = useState<AdminStats | null>(null);
  const [error, setError] = useState("");

  const [ecoForm, setEcoForm] = useState({
    cost_cny: "12",
    weight_kg: "0.3",
    length_cm: "20",
    width_cm: "15",
    height_cm: "8",
    target_margin: "15",
    first_mile: "sea",
    market_price_min: "12",
    market_price_max: "25",
    fixed_cost_cny: "3000",
  });
  const [ecoResult, setEcoResult] = useState<EconomicsResult | null>(null);
  const [ecoLoading, setEcoLoading] = useState(false);
  const [ecoError, setEcoError] = useState("");

  const load = useCallback(async () => {
    try {
      const [t, f, s] = await Promise.all([fetchAdminTasks(), fetchFiles(), fetchAdminStats()]);
      setRunning(t.tasks.filter((x) => x.status === "running" || x.status === "queued"));
      setPackages(f.packages);
      setStats(s);
      setError("");
    } catch (e) {
      setError(`连接后端失败：${String(e)}`);
    }
  }, []);

  useEffect(() => {
    load();
    const timer = setInterval(load, 5000);
    return () => clearInterval(timer);
  }, [load]);

  const fillSample = (i: number) => {
    const s = SAMPLES[i];
    setProductName(s.name);
    setSellingPoints(s.sellingPoints);
    setCategory(s.category);
  };

  const togglePlatform = (key: string) =>
    setPlatforms((prev) => (prev.includes(key) ? prev.filter((x) => x !== key) : [...prev, key]));

  const submit = async () => {
    setError("");
    if (!productName.trim() && !sellingPoints.trim()) {
      setError("先填写商品名称或卖点");
      return;
    }
    setSubmitting(true);
    try {
      const { task_id } = await createTask({
        product_name: productName.trim() || sellingPoints.trim().slice(0, 20),
        selling_points: sellingPoints.trim() || productName.trim(),
        category,
        platforms,
      });
      setProductName("");
      setSellingPoints("");
      load();
      window.open(`/result/${task_id}`, "_blank");
    } catch (e) {
      setError(`提交失败：${String(e)}`);
    } finally {
      setSubmitting(false);
    }
  };

  const numOrNull = (v: string) => (v.trim() === "" ? null : Number(v));

  const calcEconomics = async () => {
    setEcoError("");
    setEcoLoading(true);
    try {
      setEcoResult(
        await runEconomics({
          cost_cny: Number(ecoForm.cost_cny),
          weight_kg: Number(ecoForm.weight_kg),
          length_cm: Number(ecoForm.length_cm),
          width_cm: Number(ecoForm.width_cm),
          height_cm: Number(ecoForm.height_cm),
          target_margin: Number(ecoForm.target_margin) / 100,
          first_mile: ecoForm.first_mile,
          turnover_months: 2,
          fixed_cost_cny: Number(ecoForm.fixed_cost_cny) || 0,
          market_price_min: numOrNull(ecoForm.market_price_min),
          market_price_max: numOrNull(ecoForm.market_price_max),
        })
      );
    } catch (e) {
      setEcoError(`测算失败：${String(e)}`);
    } finally {
      setEcoLoading(false);
    }
  };

  const activeStage: "pre" | "on" | "post" =
    submitting || running.length > 0 ? "on" : packages.length > 0 ? "post" : "pre";

  return (
    <main className="pb-24">
      <Nav />
      <div className="mx-auto max-w-6xl px-6">
        {/* ---------- 页头 ---------- */}
        <header className="animate-fade-up pb-8 pt-10">
          <p className="eyebrow">Workbench · 工作台</p>
          <h1 className="mt-3 text-3xl font-semibold tracking-tight text-ink-900">工作台</h1>
          <p className="mt-2 text-sm text-ink-500">
            一个商品从选品到上架再到复盘，全流程在这里完成
          </p>
        </header>

        {/* ---------- 三阶段步骤条：精密仪器风 ---------- */}
        <div className="mb-8 flex items-center animate-fade-up">
          {STAGES.map((s, i) => {
            const isActive = activeStage === s.key;
            const isDone =
              (s.key === "pre" && activeStage !== "pre") || (s.key === "on" && activeStage === "post");
            return (
              <div key={s.key} className="flex flex-1 items-center">
                <div
                  className={`flex flex-1 items-center gap-3 rounded-lg border px-4 py-3 transition duration-150 ${
                    isActive
                      ? "border-brand-800 bg-brand-800 shadow-sm"
                      : isDone
                      ? "border-brand-200 bg-brand-50"
                      : "border-ink-200 bg-white"
                  }`}
                >
                  <span
                    className={`font-mono text-lg font-medium leading-none ${
                      isActive ? "text-brand-200" : isDone ? "text-brand-600" : "text-ink-300"
                    }`}
                  >
                    {String(i + 1).padStart(2, "0")}
                  </span>
                  <span className="min-w-0">
                    <span
                      className={`block text-sm font-semibold ${
                        isActive ? "text-white" : "text-ink-800"
                      }`}
                    >
                      {s.label}
                    </span>
                    <span
                      className={`block font-mono text-[10px] tracking-wide ${
                        isActive ? "text-brand-200/80" : "text-ink-400"
                      }`}
                    >
                      {isDone ? "✓ " : ""}
                      {s.desc}
                    </span>
                  </span>
                </div>
                {i < STAGES.length - 1 && (
                  <span
                    className={`mx-2 h-px w-6 shrink-0 transition duration-150 ${
                      isDone ? "bg-brand-300" : "bg-ink-200"
                    }`}
                  />
                )}
              </div>
            );
          })}
        </div>

        {error && (
          <div className="mb-4 rounded-lg bg-red-50 px-4 py-3 text-sm text-red-600">{error}</div>
        )}

        {/* ---------- 阶段一：上架前 —— 选品 / 编辑 ---------- */}
        <section className="card animate-fade-up p-6">
          <div className="flex flex-wrap items-start justify-between gap-3 border-b border-ink-100 pb-4">
            <div>
              <p className="eyebrow">Stage 01 · Pre-listing</p>
              <h2 className="mt-1.5 text-[15px] font-semibold text-ink-900">上架前 · 选品与编辑</h2>
            </div>
            <div className="flex flex-wrap items-center gap-1.5">
              <span className="spec-label mr-1">样例</span>
              {SAMPLES.map((s, i) => (
                <button
                  key={s.name}
                  onClick={() => fillSample(i)}
                  className="rounded-md border border-ink-200 bg-white px-2.5 py-1 text-xs text-ink-600 shadow-xs transition duration-150 hover:border-brand-400 hover:text-brand-700"
                >
                  {s.name}
                </button>
              ))}
            </div>
          </div>
          <div className="mt-5 grid grid-cols-1 gap-5 md:grid-cols-2">
            <div>
              <label className="spec-label mb-1.5 block">商品名称</label>
              <input
                value={productName}
                onChange={(e) => setProductName(e.target.value)}
                placeholder="例如：便携榨汁杯 380ml"
                className="field"
              />
              <label className="spec-label mb-1.5 mt-4 block">中文卖点描述</label>
              <textarea
                value={sellingPoints}
                onChange={(e) => setSellingPoints(e.target.value)}
                placeholder="一句话说清卖点，例如：USB-C 快充，10 秒出汁，杯身可拆洗"
                rows={3}
                className="field resize-none !leading-6"
              />
            </div>
            <div className="flex flex-col">
              <label className="spec-label mb-1.5 block">目标平台（点击可调整）</label>
              <div className="flex flex-wrap gap-2">
                {PLATFORM_META.map((p) => {
                  const on = platforms.includes(p.key);
                  return (
                    <button
                      key={p.key}
                      onClick={() => togglePlatform(p.key)}
                      className={`flex items-center gap-1.5 rounded-md border px-2.5 py-1.5 text-xs transition duration-150 ${
                        on
                          ? "border-brand-800 bg-brand-800 font-medium text-white shadow-sm"
                          : "border-ink-200 bg-white text-ink-500 hover:border-ink-300 hover:text-ink-700"
                      }`}
                    >
                      <span
                        className="h-1.5 w-1.5 rounded-full"
                        style={{ background: on ? p.dot : "#cdd5e0" }}
                      />
                      {p.name}
                    </button>
                  );
                })}
              </div>
              <label className="spec-label mb-1.5 mt-4 block">类目</label>
              <select
                value={category}
                onChange={(e) => setCategory(e.target.value)}
                className="field"
              >
                <option value="home_kitchen">家居厨房</option>
                <option value="electronics">3C 小家电</option>
                <option value="apparel">服饰配饰</option>
              </select>
              <button onClick={submit} disabled={submitting} className="btn-primary mt-5">
                {submitting ? "提交中…" : "生成 N 平台上架包"}
              </button>
            </div>
          </div>
        </section>

        {/* ---------- 阶段一（下）：利润测算 —— 规格说明书风 ---------- */}
        <section className="card mt-6 animate-fade-up p-6">
          <div className="flex flex-wrap items-start justify-between gap-3 border-b border-ink-100 pb-4">
            <div>
              <p className="eyebrow">Stage 01 · Economics</p>
              <h2 className="mt-1.5 text-[15px] font-semibold text-ink-900">
                上架前 · 利润测算
              </h2>
              <p className="mt-1 text-xs text-ink-400">
                持续亏本的生意没必要做 —— 先算清 5 岸单位经济再决定上不上
              </p>
            </div>
            <span className="spec-label max-w-[260px] text-right leading-4">
              费率 demo 估算（公开文档整理）· 市场带可填人工比价的最高/最低价
            </span>
          </div>

          <div className="mt-5 grid grid-cols-2 gap-2.5 sm:grid-cols-5">
            <EcoField label="采购单价" value={ecoForm.cost_cny} onChange={(v) => setEcoForm({ ...ecoForm, cost_cny: v })} suffix="¥" />
            <EcoField label="重量" value={ecoForm.weight_kg} onChange={(v) => setEcoForm({ ...ecoForm, weight_kg: v })} suffix="kg" />
            <EcoField label="包装长" value={ecoForm.length_cm} onChange={(v) => setEcoForm({ ...ecoForm, length_cm: v })} suffix="cm" />
            <EcoField label="包装宽" value={ecoForm.width_cm} onChange={(v) => setEcoForm({ ...ecoForm, width_cm: v })} suffix="cm" />
            <EcoField label="包装高" value={ecoForm.height_cm} onChange={(v) => setEcoForm({ ...ecoForm, height_cm: v })} suffix="cm" />
            <EcoField label="目标净利率" value={ecoForm.target_margin} onChange={(v) => setEcoForm({ ...ecoForm, target_margin: v })} suffix="%" />
            <label className="block">
              <span className="spec-label mb-1 block">头程方式</span>
              <select
                value={ecoForm.first_mile}
                onChange={(e) => setEcoForm({ ...ecoForm, first_mile: e.target.value })}
                className="w-full rounded-lg border border-ink-200 bg-white px-2 py-1.5 font-mono text-xs text-ink-800 shadow-xs outline-none transition duration-150 focus:border-brand-500 focus:ring-2 focus:ring-brand-100"
              >
                <option value="sea">海运 ¥8/kg</option>
                <option value="air">空运 ¥28/kg</option>
              </select>
            </label>
            <EcoField label="市场带最低价" value={ecoForm.market_price_min} onChange={(v) => setEcoForm({ ...ecoForm, market_price_min: v })} suffix="$" />
            <EcoField label="市场带最高价" value={ecoForm.market_price_max} onChange={(v) => setEcoForm({ ...ecoForm, market_price_max: v })} suffix="$" />
            <EcoField label="固定投入(认证/打样)" value={ecoForm.fixed_cost_cny} onChange={(v) => setEcoForm({ ...ecoForm, fixed_cost_cny: v })} suffix="¥" />
          </div>

          <div className="mt-4 flex flex-wrap items-center gap-3 border-t border-ink-100 pt-4">
            <button onClick={calcEconomics} disabled={ecoLoading} className="btn-primary">
              {ecoLoading ? "测算中…" : "测算 5 岸单位经济"}
            </button>
            {ecoResult && (
              <span className="flex flex-wrap items-center gap-2 font-mono text-[11px] text-ink-400">
                计费重 {ecoResult.chargeable_weight_kg}kg（体积重 {ecoResult.volume_weight_kg}kg）· 汇率 1 USD ≈{" "}
                {ecoResult.fx_usd_cny} CNY
                {ecoResult.fx_source === "live" ? (
                  <span className="flex items-center gap-1 rounded bg-green-50 px-1.5 py-0.5 font-sans text-[10px] font-medium text-green-700">
                    <span className="inline-block h-1 w-1 animate-pulse-dot rounded-full bg-green-500" />
                    实时汇率
                  </span>
                ) : (
                  <span className="rounded bg-ink-100 px-1.5 py-0.5 font-sans text-[10px] text-ink-500">内置汇率</span>
                )}
              </span>
            )}
          </div>
          {ecoError && <p className="mt-2 text-xs text-red-600">{ecoError}</p>}

          {ecoResult && (
            <div className="mt-4 rounded-lg border border-ink-100 bg-white px-4 py-3">
              <div className="flex flex-wrap gap-x-3 gap-y-1 border-b border-ink-100 pb-3">
                {ECO_SEGMENTS.map((s) => (
                  <span key={s.key} className="flex items-center gap-1 font-mono text-[10px] text-ink-400">
                    <span className="h-2 w-2 rounded-sm" style={{ background: s.color }} />
                    {s.label}
                  </span>
                ))}
              </div>
              <div className="divide-y divide-ink-100">
                {ecoResult.platforms.map((p) => (
                  <EcoRow key={p.platform} p={p} />
                ))}
              </div>
            </div>
          )}
        </section>

        {/* ---------- 阶段二：上架中 —— 生成进度 / 多平台状态 ---------- */}
        <section className="card mt-6 animate-fade-up p-6">
          <div className="flex flex-wrap items-start justify-between gap-3 border-b border-ink-100 pb-4">
            <div>
              <p className="eyebrow">Stage 02 · Generating</p>
              <h2 className="mt-1.5 text-[15px] font-semibold text-ink-900">上架中 · 生成进度</h2>
            </div>
            <span className="flex items-center gap-1.5 font-mono text-[11px] text-ink-400">
              <span className="h-1.5 w-1.5 animate-pulse-dot rounded-full bg-brand-600" />
              每 5 秒自动刷新
            </span>
          </div>
          {running.length === 0 ? (
            <p className="mt-5 rounded-lg bg-ink-50 px-4 py-6 text-center text-sm text-ink-400">
              当前没有生成中的任务 —— 从上方提交商品后，进度会实时出现在这里
            </p>
          ) : (
            <div className="mt-5 space-y-3">
              {running.map((t) => {
                const phaseIdx = PIPELINE_PHASES.findIndex((ph) =>
                  (t.stage || "").toLowerCase().includes(ph)
                );
                const progress = ((phaseIdx >= 0 ? phaseIdx + 1 : 1) / PIPELINE_PHASES.length) * 100;
                return (
                  <div key={t.task_id} className="rounded-lg border border-ink-100 bg-ink-50/60 px-4 py-3">
                    <div className="flex items-center justify-between gap-2">
                      <div className="flex min-w-0 items-center gap-2">
                        <span className="h-1.5 w-1.5 shrink-0 animate-pulse-dot rounded-full bg-brand-600" />
                        <span className="truncate text-sm font-medium text-ink-900">{t.product_name}</span>
                        <span className="font-mono text-[11px] text-ink-400">{t.stage}</span>
                      </div>
                      <Link
                        href={`/result/${t.task_id}`}
                        className="shrink-0 text-xs text-brand-700 transition duration-150 hover:text-brand-800 hover:underline"
                      >
                        查看流水线 →
                      </Link>
                    </div>
                    {/* 五阶段 mono 步骤 + 细进度条 */}
                    <div className="mt-2.5 flex items-center gap-3">
                      <div className="flex items-center gap-2">
                        {PIPELINE_PHASES.map((ph, i) => (
                          <span
                            key={ph}
                            className={`font-mono text-[10px] uppercase tracking-[0.06em] transition duration-150 ${
                              i <= phaseIdx ? "font-medium text-brand-700" : "text-ink-300"
                            }`}
                          >
                            {ph}
                          </span>
                        ))}
                      </div>
                      <div className="h-1 flex-1 overflow-hidden rounded-full bg-ink-100">
                        <div
                          className="h-full rounded-full bg-brand-600 transition-all duration-150"
                          style={{ width: `${progress}%` }}
                        />
                      </div>
                    </div>
                    <div className="mt-2.5 flex flex-wrap items-center gap-2">
                      {t.platforms.map((p) => {
                        const m = PLATFORM_META.find((x) => x.key === p);
                        return (
                          <span
                            key={p}
                            className="flex items-center gap-1.5 rounded-md border border-ink-100 bg-white px-2 py-1 text-xs text-ink-600 shadow-xs"
                          >
                            <span
                              className="h-1.5 w-1.5 animate-pulse-dot rounded-full"
                              style={{ background: m?.dot }}
                            />
                            {m?.name || p}
                          </span>
                        );
                      })}
                      <span className="ml-auto font-mono text-[10px] text-ink-400">
                        {fmtTime(t.created_at)} 提交
                      </span>
                    </div>
                  </div>
                );
              })}
            </div>
          )}
        </section>

        {/* ---------- 阶段三：上架后 —— 文件 / 导出 / 复盘 ---------- */}
        <section className="card mt-6 animate-fade-up p-6">
          <div className="flex flex-wrap items-start justify-between gap-3 border-b border-ink-100 pb-4">
            <div>
              <p className="eyebrow">Stage 03 · Post-listing</p>
              <h2 className="mt-1.5 text-[15px] font-semibold text-ink-900">上架后 · 文件与复盘</h2>
            </div>
            {stats && (
              <div className="flex gap-4 font-mono text-[11px] text-ink-500">
                <span>
                  合规通过率{" "}
                  <b className="font-semibold text-emerald-600">
                    {Math.round(stats.compliance.pass_rate * 100)}%
                  </b>
                </span>
                <span>
                  自愈修订 <b className="font-semibold text-rose-600">{stats.self_heal.revised_total}</b>
                </span>
                <span>
                  生成主图 <b className="font-semibold text-ink-900">{stats.images}</b>
                </span>
              </div>
            )}
          </div>
          {packages.length === 0 ? (
            <p className="mt-5 rounded-lg bg-ink-50 px-4 py-6 text-center text-sm text-ink-400">
              还没有完成的上架包 —— 生成完成后，文件与复盘数据会出现在这里
            </p>
          ) : (
            <div className="mt-5 grid grid-cols-1 gap-3 md:grid-cols-2">
              {packages.map((pkg) => (
                <div
                  key={pkg.task_id}
                  className="rounded-lg border border-ink-100 bg-white p-4 transition duration-150 hover:shadow-sm"
                >
                  <div className="flex items-start justify-between gap-2">
                    <div className="min-w-0">
                      <p className="truncate text-sm font-medium text-ink-900">{pkg.product_name}</p>
                      <p className="mt-0.5 max-w-[220px] truncate font-mono text-[10px] text-ink-400">
                        {pkg.task_id}
                      </p>
                    </div>
                    {pkg.revised_total > 0 && (
                      <span className="shrink-0 rounded bg-rose-50 px-1.5 py-0.5 font-mono text-[10px] font-medium text-rose-600">
                        自愈 ×{pkg.revised_total}
                      </span>
                    )}
                  </div>
                  <div className="mt-2.5 flex flex-wrap gap-1.5">
                    {pkg.platforms_done.map((p) => {
                      const m = PLATFORM_META.find((x) => x.key === p.platform);
                      return (
                        <span
                          key={p.platform}
                          className={`flex items-center gap-1 rounded px-1.5 py-0.5 font-mono text-[10px] font-medium ${
                            p.passed ? "bg-emerald-50 text-emerald-600" : "bg-red-50 text-red-600"
                          }`}
                        >
                          <span
                            className="h-1 w-1 rounded-full"
                            style={{ background: m?.dot || "#cdd5e0" }}
                          />
                          {m?.name || p.platform} {p.passed ? "✓" : "✗"}
                        </span>
                      );
                    })}
                  </div>
                  <div className="mt-3 flex items-center justify-between border-t border-ink-100 pt-2.5">
                    <span className="spec-label leading-4">
                      {pkg.platforms_done.filter((p) => p.passed).length}/{pkg.platforms_done.length} 合规 ·{" "}
                      {pkg.files.length} 个文件 · {fmtSize(pkg.total_size)}
                      {pkg.done_at && pkg.created_at
                        ? ` · ${Math.round(pkg.done_at - pkg.created_at)}s 完成`
                        : ""}
                    </span>
                    <div className="flex shrink-0 gap-2 text-xs">
                      <Link
                        href={`/result/${pkg.task_id}`}
                        className="text-brand-700 transition duration-150 hover:text-brand-800 hover:underline"
                      >
                        查看
                      </Link>
                      <Link
                        href="/files"
                        className="text-ink-500 transition duration-150 hover:text-ink-700 hover:underline"
                      >
                        文件 →
                      </Link>
                    </div>
                  </div>
                </div>
              ))}
            </div>
          )}
        </section>
      </div>
    </main>
  );
}
