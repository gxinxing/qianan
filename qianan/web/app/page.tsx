"use client";

import { useEffect, useRef, useState } from "react";
import { useRouter } from "next/navigation";
import Nav from "@/components/Nav";
import Footer from "@/components/Footer";
import {
  createTask,
  fetchTrends,
  PLATFORM_META,
  requestIdeation,
  CompetitorBand,
  IdeationSuggestion,
} from "@/lib/api";
import { SAMPLES } from "@/lib/samples";

const MARKETS = [
  { key: "us", name: "美国" },
  { key: "sea", name: "东南亚" },
  { key: "global", name: "全球" },
];

const IDEA_CATEGORIES = [
  { key: "home_kitchen", name: "家居厨房" },
  { key: "electronics", name: "3C 小家电" },
  { key: "apparel", name: "服饰配饰" },
];

const CAPABILITIES = [
  {
    no: "01",
    en: "RULES ENGINE",
    title: "多平台规则引擎",
    desc: "合规是代码校验出来的，不是模型声称的。",
    points: ["38 条结构化合规校验", "88 词跨平台禁用词库", "5 平台字段级规范模板"],
  },
  {
    no: "02",
    en: "LOCALIZATION",
    title: "多语言本地化",
    desc: "按市场购物习惯重写，而非生硬直译。",
    points: ["9 种语言原生改写", "12 个站点 locale 适配", "平台字符集与长度预检"],
  },
  {
    no: "03",
    en: "SELF-HEALING",
    title: "合规预检与自愈",
    desc: "error 级问题自动回炉修订，复检留痕。",
    points: ["禁用词 / 超限自动修复", "修订次数全程可溯", "通过率纳入后台统计"],
  },
];

/* Agent Trace 演示数据：与后端真实 plan/build/heal/reflect/evolve 五阶段对应 */
const TRACE_DEMO = [
  { phase: "plan", tool: "understand_product", summary: "识别品类 · 提取 3 个核心卖点", status: "ok" },
  { phase: "build", tool: "draft_listing", summary: "Amazon · en-US 标题与五点描述", status: "ok" },
  { phase: "build", tool: "localize", summary: "Shopee · th-TH 原生改写", status: "ok" },
  { phase: "heal", tool: "fix_banned_word", summary: "命中禁用词「best」· 自动修订复检通过", status: "run" },
  { phase: "reflect", tool: "review_package", summary: "待执行 · 产出物一致性复核", status: "wait" },
  { phase: "evolve", tool: "distill_lesson", summary: "待执行 · 经验沉淀入记忆库", status: "wait" },
] as const;

function AgentTracePanel() {
  return (
    <div className="trace-panel w-full max-w-md rounded-xl p-5">
      <div className="flex items-center justify-between">
        <p className="font-mono text-[10px] font-medium uppercase tracking-[0.1em] text-brand-300">
          Agent Trace · Live
        </p>
        <span className="flex items-center gap-1.5 font-mono text-[10px] text-emerald-400">
          <span className="h-1.5 w-1.5 animate-pulse-dot rounded-full bg-emerald-400" />
          RUNNING
        </span>
      </div>
      <div className="mt-4 space-y-1">
        {TRACE_DEMO.map((t, i) => (
          <div
            key={i}
            data-status={t.status}
            className="trace-row flex items-start gap-3 rounded-r-md py-2 pl-3 pr-2"
          >
            <span
              className={`mt-0.5 font-mono text-[10px] font-semibold uppercase tracking-[0.08em] ${
                t.status === "ok"
                  ? "text-emerald-400"
                  : t.status === "run"
                    ? "text-brand-300"
                    : "text-brand-200/40"
              }`}
            >
              {String(i + 1).padStart(2, "0")}
            </span>
            <div className="min-w-0 flex-1">
              <p
                className={`font-mono text-[11px] font-medium ${
                  t.status === "wait" ? "text-brand-200/40" : "text-brand-100"
                }`}
              >
                {t.phase}
                <span className="mx-1.5 text-brand-200/30">·</span>
                <span className={t.status === "wait" ? "text-brand-200/40" : "text-brand-300"}>
                  {t.tool}
                </span>
              </p>
              <p
                className={`mt-0.5 truncate text-[11px] leading-4 ${
                  t.status === "wait" ? "text-brand-200/30" : "text-brand-100/60"
                }`}
              >
                {t.summary}
              </p>
            </div>
            {t.status === "run" && (
              <span className="mt-1 h-1.5 w-1.5 shrink-0 animate-pulse-dot rounded-full bg-brand-300" />
            )}
            {t.status === "ok" && (
              <span className="mt-1 shrink-0 text-[10px] text-emerald-400">✓</span>
            )}
          </div>
        ))}
      </div>
      <div className="mt-3 border-t border-white/5 pt-3">
        <p className="font-mono text-[10px] text-brand-200/40">
          plan → build → heal → reflect → evolve
        </p>
      </div>
    </div>
  );
}

/* ---------- 产出物微缩样机（纯 CSS，对应真实上架包内容） ---------- */

function MockCopy() {
  return (
    <div className="flex h-full flex-col gap-1.5 p-3">
      <div className="h-2 w-4/5 rounded-sm bg-ink-800" />
      <div className="h-1.5 w-3/5 rounded-sm bg-ink-300" />
      <div className="mt-1.5 space-y-1.5">
        {["USB-C fast charge, 10s blending", "Detachable cup, easy to clean", "Only 380g, carry anywhere"].map(
          (t) => (
            <div key={t} className="flex items-center gap-1.5">
              <span className="h-0.5 w-0.5 rounded-full bg-brand-600" />
              <span className="truncate text-[9px] leading-3 text-ink-500">{t}</span>
            </div>
          ),
        )}
      </div>
      <div className="mt-auto flex items-center gap-1">
        <span className="rounded-sm bg-brand-50 px-1 py-0.5 font-mono text-[8px] text-brand-700">en-US</span>
        <span className="rounded-sm bg-ink-50 px-1 py-0.5 font-mono text-[8px] text-ink-400">th-TH</span>
        <span className="rounded-sm bg-ink-50 px-1 py-0.5 font-mono text-[8px] text-ink-400">vi-VN</span>
      </div>
    </div>
  );
}

function MockImage() {
  return (
    <div className="flex h-full flex-col items-center justify-center gap-2 p-3">
      <div className="flex h-16 w-16 items-center justify-center rounded-md bg-white ring-1 ring-ink-200">
        <div className="h-9 w-7 rounded-b-lg rounded-t-sm bg-gradient-to-b from-brand-200 to-brand-400" />
      </div>
      <div className="flex flex-wrap items-center justify-center gap-1">
        <span className="rounded-sm bg-emerald-50 px-1 py-0.5 font-mono text-[8px] text-emerald-700">
          ✓ 白底
        </span>
        <span className="rounded-sm bg-emerald-50 px-1 py-0.5 font-mono text-[8px] text-emerald-700">
          ✓ 1000×1000
        </span>
        <span className="rounded-sm bg-emerald-50 px-1 py-0.5 font-mono text-[8px] text-emerald-700">
          ✓ 无文字
        </span>
      </div>
    </div>
  );
}

function MockAplus() {
  return (
    <div className="flex h-full flex-col gap-1.5 p-3">
      <div className="h-2.5 w-2/3 rounded-sm bg-ink-800" />
      <div className="grid flex-1 grid-cols-3 gap-1">
        {[0, 1, 2].map((i) => (
          <div key={i} className="flex flex-col gap-1">
            <div className="flex-1 rounded-sm bg-gradient-to-b from-brand-100 to-brand-200/60" />
            <div className="h-1 w-full rounded-sm bg-ink-200" />
          </div>
        ))}
      </div>
      <div className="space-y-1">
        <div className="h-1 w-full rounded-sm bg-ink-200" />
        <div className="h-1 w-4/5 rounded-sm bg-ink-200" />
      </div>
    </div>
  );
}

function MockCsv() {
  return (
    <div className="flex h-full flex-col p-3">
      <div className="grid grid-cols-3 overflow-hidden rounded-sm ring-1 ring-ink-200">
        {["sku", "title", "price", "QB-380", "Portable…", "$24.9", "QB-381", "Blender…", "$26.9"].map(
          (c, i) => (
            <div
              key={i}
              className={`truncate border-b border-r border-ink-100 px-1 py-1 font-mono text-[8px] leading-3 ${
                i < 3 ? "bg-ink-50 font-medium text-ink-600" : "bg-white text-ink-400"
              }`}
            >
              {c}
            </div>
          ),
        )}
      </div>
      <p className="mt-auto pt-2 font-mono text-[8px] text-ink-400">amazon_flatfile.csv · shopee_mass.xlsx</p>
    </div>
  );
}

function MockCompliance() {
  return (
    <div className="flex h-full flex-col gap-1.5 p-3">
      {[
        { t: "title_length ≤ 200", ok: true },
        { t: "banned_words × 0", ok: true },
        { t: "required_attrs 8/8", ok: true },
      ].map((r) => (
        <div key={r.t} className="flex items-center gap-1.5">
          <span className="text-[9px] text-emerald-600">✓</span>
          <span className="font-mono text-[9px] leading-3 text-ink-500">{r.t}</span>
        </div>
      ))}
      <div className="mt-auto rounded-sm bg-brand-50 px-1.5 py-1 text-[9px] leading-3 text-brand-700">
        2 error 已自愈 · 复检通过
      </div>
    </div>
  );
}

const ARTIFACTS = [
  { key: "copy", en: "LISTING COPY", name: "多语言文案", desc: "标题 / 五点 / 详情，按平台语气重写", Mock: MockCopy },
  { key: "image", en: "MAIN IMAGE", name: "规范主图", desc: "白底、尺寸、无文字逐条达标", Mock: MockImage },
  { key: "aplus", en: "A+ CONTENT", name: "A+ 详情", desc: "模块化详情页，讲述品牌卖点", Mock: MockAplus },
  { key: "csv", en: "IMPORT FILE", name: "后台导入表", desc: "平台模板直出，下载即可上传", Mock: MockCsv },
  { key: "compliance", en: "COMPLIANCE", name: "合规报告", desc: "38 项体检结果与自愈留痕", Mock: MockCompliance },
];

export default function HomePage() {
  const router = useRouter();
  const fileRef = useRef<HTMLInputElement>(null);
  const [productName, setProductName] = useState("");
  const [sellingPoints, setSellingPoints] = useState("");
  const [category, setCategory] = useState("home_kitchen");
  const [imageBase64, setImageBase64] = useState("");
  const [preview, setPreview] = useState("");
  const [platforms, setPlatforms] = useState<string[]>(PLATFORM_META.map((p) => p.key));
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [market, setMarket] = useState("sea");
  const [ideaCategory, setIdeaCategory] = useState("home_kitchen");
  const [ideaLoading, setIdeaLoading] = useState(false);
  const [ideas, setIdeas] = useState<IdeationSuggestion[]>([]);
  const [ideaError, setIdeaError] = useState("");
  const [trends, setTrends] = useState<string[]>([]);
  const [band, setBand] = useState<CompetitorBand | null>(null);

  const onFile = (file: File | undefined) => {
    if (!file) return;
    const reader = new FileReader();
    reader.onload = () => {
      const result = String(reader.result);
      setImageBase64(result.split(",")[1] || "");
      setPreview(result);
    };
    reader.readAsDataURL(file);
  };

  const togglePlatform = (key: string) =>
    setPlatforms((prev) => (prev.includes(key) ? prev.filter((x) => x !== key) : [...prev, key]));

  const fillSample = (i: number) => {
    const s = SAMPLES[i];
    setProductName(s.name);
    setSellingPoints(s.sellingPoints);
    setCategory(s.category);
    setError("");
  };

  // 实时热搜 chips：装了趋势连接器才有词，未装则静默隐藏（不影响选品主流程）
  useEffect(() => {
    let alive = true;
    fetchTrends(market)
      .then((r) => {
        if (alive) setTrends(r.trend_source === "live" ? r.trends : []);
      })
      .catch(() => {
        if (alive) setTrends([]);
      });
    return () => {
      alive = false;
    };
  }, [market]);

  const genIdeation = async () => {
    setIdeaError("");
    setIdeaLoading(true);
    try {
      const r = await requestIdeation(market, ideaCategory);
      setIdeas(r.suggestions);
      if (r.trend_source === "live" && r.trends?.length) setTrends(r.trends);
      setBand(r.competitor_band || null);
    } catch (e) {
      setIdeaError(`选品建议生成失败：${String(e)}`);
    } finally {
      setIdeaLoading(false);
    }
  };

  const useIdea = (idea: IdeationSuggestion) => {
    setProductName(idea.product_name);
    setSellingPoints(idea.selling_points);
    setCategory(idea.category);
    setError("");
    window.scrollTo({ top: 0, behavior: "smooth" });
  };

  const submit = async () => {
    setError("");
    if (!productName.trim() && !sellingPoints.trim()) {
      setError("先描述一下你的商品，或点下方样例商品快速体验");
      return;
    }
    if (!platforms.length) {
      setError("请至少选择一个目标平台");
      return;
    }
    setLoading(true);
    try {
      const { task_id } = await createTask({
        product_name: productName.trim() || sellingPoints.trim().slice(0, 20),
        selling_points: sellingPoints.trim() || productName.trim(),
        category,
        image_base64: imageBase64 || undefined,
        platforms,
      });
      router.push(`/result/${task_id}`);
    } catch (e) {
      setError(`无法连接后端：${String(e)}`);
      setLoading(false);
    }
  };

  return (
    <main>
      <Nav />

      {/* ---------- Hero：深海图 + Agent Trace ---------- */}
      <section className="contour-bg relative overflow-hidden">
        <div className="mx-auto max-w-6xl px-6 pb-36 pt-12">
          {/* 赛事公告条（Supabase 式） */}
          <div className="flex justify-center">
            <span className="inline-flex max-w-full items-center gap-2 rounded-full border border-brand-400/25 bg-white/5 px-3.5 py-1.5 font-mono text-[11px] tracking-[0.04em] text-brand-200 backdrop-blur">
              <span className="sm:hidden">AI+跨境黑客松 · 复赛 Demo</span>
              <span className="hidden sm:inline">AI+跨境黑客松巅峰赛 · 复赛</span>
              <span className="hidden h-3 w-px bg-brand-400/30 sm:inline" />
              <span className="hidden text-brand-300 sm:inline">多平台智能上新 Agent →</span>
            </span>
          </div>

          <div className="mt-14 grid items-center gap-12 lg:grid-cols-[1.2fr_1fr]">
            {/* 左：标题组 */}
            <div>
              {/* 实时数据眉题（Stripe 式） */}
              <p className="eyebrow !text-brand-300 animate-fade-up flex items-center gap-2">
                <span className="relative flex h-1.5 w-1.5">
                  <span className="absolute inline-flex h-full w-full animate-ping rounded-full bg-emerald-400 opacity-60" />
                  <span className="relative inline-flex h-1.5 w-1.5 rounded-full bg-emerald-400" />
                </span>
                Rules Engine Online · 38 Checks · 5 Platforms · 10 Locales
              </p>

              <h1 className="mt-5 text-[52px] font-semibold leading-[1.05] tracking-[-0.02em] text-white sm:text-[72px]">
                一稿多岸
              </h1>
              <p className="mt-4 max-w-xl text-xl leading-snug sm:text-2xl">
                <span className="text-white">一件商品，一次输入，</span>
                <span className="text-brand-300">五片海岸各自合规。</span>
              </p>
              <p className="mt-5 max-w-lg text-[15px] leading-7 text-brand-100/70">
                AI 按 5 个平台的结构化规则引擎，生成各自合规、可直接导入的上架包——
                多语言文案、规范主图、A+ 详情、后台导入表，下载即用。
              </p>

              {/* 平台墙（Vercel/Stripe 式 logo 带） */}
              <div className="mt-10 border-t border-white/10 pt-5">
                <div className="flex flex-wrap items-center gap-x-7 gap-y-3">
                  {PLATFORM_META.map((p) => (
                    <div key={p.key} className="flex items-center gap-2">
                      <span
                        className="h-1.5 w-1.5 rounded-full"
                        style={{ background: p.key === "tiktokshop" ? "#e3e8f0" : p.dot }}
                      />
                      <span className="text-[13px] font-semibold tracking-wide text-brand-100/80">
                        {p.name}
                      </span>
                    </div>
                  ))}
                </div>
              </div>
            </div>

            {/* 右：Agent Trace 产品证明面板（Linear 式） */}
            <div className="hidden justify-end lg:flex">
              <AgentTracePanel />
            </div>
          </div>
        </div>
        <div className="pointer-events-none absolute inset-x-0 bottom-0 h-16 bg-gradient-to-b from-transparent to-[#f2f5fb]" />
      </section>

      {/* ---------- 输入卡片（压 Hero 边） ---------- */}
      <section className="mx-auto max-w-6xl px-6">
        <div className="card relative z-10 -mt-24 p-6 shadow-lg">
          <div className="flex items-center justify-between">
            <p className="eyebrow">New Listing · 新建上架任务</p>
            <p className="font-mono text-[11px] text-ink-400">
              {platforms.length}/{PLATFORM_META.length} SHORES
            </p>
          </div>

          <div className="mt-4 flex flex-col gap-4 sm:flex-row">
            <div
              onClick={() => fileRef.current?.click()}
              className="group flex h-28 w-full shrink-0 cursor-pointer flex-col items-center justify-center overflow-hidden rounded-lg border border-dashed border-ink-300 bg-ink-50 text-center transition hover:border-brand-500 hover:bg-brand-50 sm:h-32 sm:w-32"
            >
              {preview ? (
                // eslint-disable-next-line @next/next/no-img-element
                <img src={preview} alt="商品图" className="h-full w-full object-cover" />
              ) : (
                <>
                  <span className="font-mono text-lg text-ink-300 transition group-hover:text-brand-500">+</span>
                  <span className="mt-1 px-2 text-[11px] leading-4 text-ink-400">
                    拖入或点击上传商品图
                  </span>
                </>
              )}
            </div>
            <input
              ref={fileRef}
              type="file"
              accept="image/*"
              className="hidden"
              onChange={(e) => onFile(e.target.files?.[0])}
            />

            <div className="flex min-w-0 flex-1 flex-col gap-3">
              <input
                value={productName}
                onChange={(e) => setProductName(e.target.value)}
                placeholder="商品名称，如：便携榨汁杯 380ml"
                className="field !text-[15px] !font-medium"
              />
              <textarea
                value={sellingPoints}
                onChange={(e) => setSellingPoints(e.target.value)}
                rows={2}
                placeholder="一句话卖点，如：USB-C 快充，10 秒出汁，杯身可拆洗，仅 380g…"
                className="field flex-1 resize-none !leading-6"
              />
            </div>
          </div>

          <div className="mt-5 flex flex-wrap items-center justify-between gap-4 border-t border-ink-100 pt-4">
            <div className="flex flex-wrap items-center gap-2">
              <span className="spec-label mr-1">目标平台</span>
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

            <button onClick={submit} disabled={loading} className="btn-primary">
              {loading ? "提交中…" : `生成 ${platforms.length} 平台上架包 →`}
            </button>
          </div>

          {error && <p className="mt-3 text-sm text-red-600">{error}</p>}
        </div>

        {/* 样例商品 */}
        <div className="mt-4 flex flex-wrap items-center gap-2">
          <span className="spec-label">没有商品？试试样例</span>
          {SAMPLES.map((s, i) => (
            <button
              key={s.name}
              onClick={() => fillSample(i)}
              className="rounded-md border border-ink-200 bg-white px-2.5 py-1 text-xs text-ink-600 shadow-xs transition hover:border-brand-400 hover:text-brand-700"
            >
              {s.name}
            </button>
          ))}
        </div>
      </section>

      {/* ---------- 产出物证明（Linear 式：直接展示产品输出） ---------- */}
      <section className="mx-auto mt-20 max-w-6xl px-6">
        <div className="flex flex-wrap items-end justify-between gap-4">
          <div>
            <p className="eyebrow">Deliverables · 产出物</p>
            <h2 className="mt-2 text-2xl font-semibold tracking-tight text-ink-900">
              一次输入，五份产出
            </h2>
            <p className="mt-1.5 text-sm text-ink-500">
              每个平台一个独立上架包，以下为包内真实产物的微缩预览
            </p>
          </div>
          <p className="font-mono text-[11px] text-ink-400">PER PLATFORM / PER PACKAGE</p>
        </div>

        <div className="mt-6 grid gap-4 sm:grid-cols-2 lg:grid-cols-5">
          {ARTIFACTS.map((a) => (
            <div key={a.key} className="card group flex flex-col overflow-hidden transition hover:shadow-md">
              <div className="border-b border-ink-100 bg-ink-50/60 px-4 py-2.5">
                <p className="font-mono text-[9px] font-medium uppercase tracking-[0.1em] text-ink-400">
                  {a.en}
                </p>
              </div>
              <div className="h-36">
                <a.Mock />
              </div>
              <div className="border-t border-ink-100 p-4">
                <h3 className="text-[13px] font-semibold text-ink-900">{a.name}</h3>
                <p className="mt-1 text-[11px] leading-4 text-ink-500">{a.desc}</p>
              </div>
            </div>
          ))}
        </div>
      </section>

      {/* ---------- 选品灵感 ---------- */}
      <section className="mx-auto mt-20 max-w-6xl px-6">
        <div className="flex flex-wrap items-end justify-between gap-4">
          <div>
            <p className="eyebrow">Ideation · 选品灵感</p>
            <h2 className="mt-2 text-2xl font-semibold tracking-tight text-ink-900">
              不知道卖什么？AI 帮你选品
            </h2>
            <p className="mt-1.5 text-sm text-ink-500">
              选市场与类目，生成 3 条值得卖的建议，一键进入上架流水线
            </p>
          </div>
          <div className="flex flex-wrap items-center gap-2">
            <div className="segment">
              {MARKETS.map((m) => (
                <button
                  key={m.key}
                  data-on={market === m.key}
                  onClick={() => setMarket(m.key)}
                  className="segment-item"
                >
                  {m.name}
                </button>
              ))}
            </div>
            <div className="segment">
              {IDEA_CATEGORIES.map((c) => (
                <button
                  key={c.key}
                  data-on={ideaCategory === c.key}
                  onClick={() => setIdeaCategory(c.key)}
                  className="segment-item"
                >
                  {c.name}
                </button>
              ))}
            </div>
            <button onClick={genIdeation} disabled={ideaLoading} className="btn-primary !px-4 !py-2 !text-xs">
              {ideaLoading ? "AI 分析中…" : "生成选品建议"}
            </button>
          </div>
        </div>

        {trends.length > 0 && (
          <div className="mt-4 flex flex-wrap items-center gap-2">
            <span className="flex items-center gap-1.5 font-mono text-[11px] uppercase tracking-[0.06em] text-ink-400">
              <span className="inline-block h-1.5 w-1.5 animate-pulse-dot rounded-full bg-emerald-500" />
              实时热搜 · {MARKETS.find((m) => m.key === market)?.name}
            </span>
            {trends.map((t) => (
              <span key={t} className="rounded-full bg-ink-100 px-2.5 py-1 text-[11px] text-ink-600">
                {t}
              </span>
            ))}
          </div>
        )}

        {ideaError && <p className="mt-3 text-sm text-red-600">{ideaError}</p>}

        {ideas.length > 0 && (
          <div className="mt-6 grid gap-4 md:grid-cols-3">
            {ideas.map((idea, idx) => (
              <div key={idea.product_name} className="card flex flex-col p-5 transition hover:shadow-md">
                <p className="spec-label">候选 {String(idx + 1).padStart(2, "0")}</p>
                <h3 className="mt-2 text-[15px] font-semibold text-ink-900">{idea.product_name}</h3>
                <p className="mt-2 flex-1 text-[13px] leading-6 text-ink-500">{idea.reason}</p>
                <p className="mt-3 border-t border-ink-100 pt-3 text-xs leading-5 text-ink-400">
                  {idea.selling_points}
                </p>
                <button
                  onClick={() => useIdea(idea)}
                  className="btn-primary mt-4 !w-full !py-2 !text-xs"
                >
                  上架这个 →
                </button>
              </div>
            ))}
          </div>
        )}

        {ideas.length > 0 && band && (
          <p className="mt-4 flex flex-wrap items-center gap-2 text-xs text-ink-400">
            <span className="rounded bg-brand-50 px-1.5 py-0.5 font-medium text-brand-700">竞品价格带</span>
            该类目主流在售 ${band.price_min} – ${band.price_max} {band.currency}
            {band.samples?.length ? `· ${band.samples.join("；")}` : ""}
            <span className="text-ink-300">（连接器演示数据）</span>
          </p>
        )}
      </section>

      {/* ---------- 能力规格（Supabase 式：图标 + 清单） ---------- */}
      <section className="mx-auto mt-20 max-w-6xl px-6">
        <p className="eyebrow">Capabilities · 核心能力</p>
        <div className="mt-4 grid gap-px overflow-hidden rounded-xl bg-ink-100 ring-1 ring-ink-100 sm:grid-cols-3">
          {CAPABILITIES.map((f) => (
            <div key={f.no} className="flex flex-col bg-white p-6">
              <div className="flex items-baseline justify-between">
                <span className="font-mono text-2xl font-medium text-brand-200">{f.no}</span>
                <span className="spec-label">{f.en}</span>
              </div>
              <h3 className="mt-4 text-[15px] font-semibold text-ink-900">{f.title}</h3>
              <p className="mt-1.5 text-[13px] leading-6 text-ink-500">{f.desc}</p>
              <ul className="mt-4 space-y-2 border-t border-ink-100 pt-4">
                {f.points.map((pt) => (
                  <li key={pt} className="flex items-center gap-2 text-[12px] text-ink-600">
                    <span className="text-[10px] text-emerald-600">✓</span>
                    {pt}
                  </li>
                ))}
              </ul>
            </div>
          ))}
        </div>
      </section>

      {/* ---------- 收尾 CTA ---------- */}
      <section className="mx-auto mt-20 max-w-6xl px-6">
        <div className="contour-bg relative overflow-hidden rounded-2xl px-8 py-14 text-center">
          <p className="eyebrow !text-brand-300">Ready to Ship</p>
          <h2 className="mx-auto mt-3 max-w-xl text-3xl font-semibold tracking-tight text-white">
            准备好把商品铺上五片海岸了吗？
          </h2>
          <p className="mx-auto mt-3 max-w-md text-sm leading-6 text-brand-100/70">
            填入商品名称与一句话卖点，两分钟取回五套合规上架包。
          </p>
          <button
            onClick={() => window.scrollTo({ top: 0, behavior: "smooth" })}
            className="mt-6 inline-flex items-center gap-2 rounded-lg bg-white px-6 py-3 text-sm font-semibold text-brand-900 shadow-lg transition hover:bg-brand-50 active:translate-y-px"
          >
            立即创建上架任务 ↑
          </button>
        </div>
      </section>

      <Footer />
    </main>
  );
}
