"use client";

import { useEffect, useRef, useState } from "react";
import { useRouter } from "next/navigation";
import Link from "next/link";
import { ArrowUp, ArrowUpRight, Plus, SlidersHorizontal, Globe2, Package, PanelLeft, X, Layers, FolderOpen, BookOpen, Sparkles } from "lucide-react";
import { Enter, PressButton, Reveal, Feedback, SidebarMotion } from "@/components/MotionUI";
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

/** 诉求快捷短语：一键填入，演示与日常使用都不用打字。 */
const REQUEST_PRESETS = [
  { label: "出完整包", text: "帮我出一套完整的上架包" },
  { label: "先看方案", text: "先别生成，我想看看你打算怎么做" },
  { label: "只要东南亚", text: "只铺 Shopee、Lazada 和 TikTok Shop" },
];

const LAUNCH_FLOW = [
  { no: "01", title: "商品事实", desc: "图片 / 文档提取，标记证据与缺口" },
  { no: "02", title: "平台适配", desc: "标题、属性、图片按渠道规则生成" },
  { no: "03", title: "合规预检", desc: "禁用词、字段、尺寸问题自动修复" },
  { no: "04", title: "发布回执", desc: "提交后台并返回链接，失败可重试" },
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

/** 原始文件大小上限：10MB（超限直接提示，不做压缩）。 */
const MAX_UPLOAD_BYTES = 10 * 1024 * 1024;

/**
 * Canvas 压缩：最长边 ≤ maxEdge、JPEG 质量 quality。
 * 透明区域填白（电商主图白底规范），压缩失败由调用方回退原图。
 */
function compressImage(dataUrl: string, maxEdge = 1600, quality = 0.85): Promise<string> {
  return new Promise((resolve, reject) => {
    const img = new Image();
    img.onload = () => {
      const scale = Math.min(1, maxEdge / Math.max(img.width, img.height));
      const w = Math.max(1, Math.round(img.width * scale));
      const h = Math.max(1, Math.round(img.height * scale));
      const canvas = document.createElement("canvas");
      canvas.width = w;
      canvas.height = h;
      const ctx = canvas.getContext("2d");
      if (!ctx) {
        reject(new Error("canvas 2d context unavailable"));
        return;
      }
      ctx.fillStyle = "#ffffff";
      ctx.fillRect(0, 0, w, h);
      ctx.drawImage(img, 0, 0, w, h);
      resolve(canvas.toDataURL("image/jpeg", quality));
    };
    img.onerror = () => reject(new Error("image decode failed"));
    img.src = dataUrl;
  });
}

export default function HomePage() {
  const router = useRouter();
  const fileRef = useRef<HTMLInputElement>(null);
  const [productName, setProductName] = useState("");
  const [sellingPoints, setSellingPoints] = useState("");
  const [requestText, setRequestText] = useState("");
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
  const [dragOver, setDragOver] = useState(false);
  const [settingsOpen, setSettingsOpen] = useState(false);
  const [menuOpen, setMenuOpen] = useState(false);

  /** 清空已选图片，回到未上传态（重新选择同一文件也能再次触发 change）。 */
  const clearImage = () => {
    setImageBase64("");
    setPreview("");
    setError("");
    if (fileRef.current) fileRef.current.value = "";
  };

  const onFile = (file: File | undefined) => {
    if (!file) return;
    if (file.size > MAX_UPLOAD_BYTES) {
      setError(`图片过大（${(file.size / 1024 / 1024).toFixed(1)}MB），请上传 10MB 以内的图片`);
      return;
    }
    const reader = new FileReader();
    reader.onload = () => {
      const result = String(reader.result);
      // 压缩（最长边 ≤1600px、JPEG 0.85）后再走现有 base64 流程，避免大图撑爆请求体
      compressImage(result)
        .then((compressed) => {
          setImageBase64(compressed.split(",")[1] || "");
          setPreview(compressed);
          setError("");
        })
        .catch(() => {
          // 压缩失败（如图片解码异常）：回退原图，保证流程可用
          setImageBase64(result.split(",")[1] || "");
          setPreview(result);
          setError("");
        });
    };
    reader.onerror = () => setError("图片读取失败，请换一张试试");
    reader.readAsDataURL(file);
  };

  const togglePlatform = (key: string) =>
    setPlatforms((prev) => (prev.includes(key) ? prev.filter((x) => x !== key) : [...prev, key]));

  const fillSample = (i: number) => {
    const s = SAMPLES[i];
    setProductName(s.name);
    setSellingPoints(`${s.name}，${s.sellingPoints}`);
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
    setSellingPoints(`${idea.product_name}，${idea.selling_points}`);
    setCategory(idea.category);
    setError("");
    window.scrollTo({ top: 0, behavior: "smooth" });
  };

  const submit = async () => {
    setError("");
    if (!productName.trim() && !sellingPoints.trim() && !imageBase64) {
      setError("上传一张商品图，或填写商品名称 / 卖点，即可生成上架包");
      return;
    }
    if (!platforms.length) {
      setError("请至少选择一个目标平台");
      return;
    }
    setLoading(true);
    try {
      const { task_id } = await createTask({
        product_name: productName.trim() || sellingPoints.trim().slice(0, 200),
        selling_points: sellingPoints.trim(),
        request_text: requestText.trim() || sellingPoints.trim().slice(0, 300),
        category,
        image_base64: imageBase64 || undefined,
        platforms,
      });
      router.push(`/result?taskId=${task_id}`);
    } catch (e) {
      setError(`无法连接后端：${String(e)}`);
      setLoading(false);
    }
  };

  return (
    <main className="agent-home">
      <SidebarMotion open={menuOpen} onClose={() => setMenuOpen(false)}>
        <Link href="/" className="agent-home-brand"><span>岸</span>千岸 <small>QianAn</small></Link>
        <PressButton className="agent-home-new" onClick={() => { setProductName(""); setSellingPoints(""); setRequestText(""); clearImage(); setMenuOpen(false); }}><Plus size={17} /> 新建任务</PressButton>
        <nav aria-label="工作区导航">
          <Link href="/workbench"><Layers size={17} />任务工作台<ArrowUpRight size={13} /></Link>
          <Link href="/studio"><Sparkles size={17} />对话 Studio<ArrowUpRight size={13} /></Link>
          <Link href="/files"><FolderOpen size={17} />我的文件</Link>
          <Link href="/batch"><Package size={17} />批量上新</Link>
          <p>工作区</p>
          <Link href="/rules"><BookOpen size={17} />平台规则</Link>
          <Link href="/agent"><Globe2 size={17} />Agent 中枢</Link>
        </nav>
        <div className="agent-home-sidebar-note"><span>一稿多岸</span><p>从一件商品，到下一个市场。</p><Link href="/login">账户与登录 <ArrowUpRight size={14} /></Link></div>
      </SidebarMotion>
      {menuOpen && <PressButton className="agent-home-backdrop" aria-label="关闭导航" onClick={() => setMenuOpen(false)} />}
      <div className="agent-home-content">
        <header className="agent-home-topbar">
          <div><PressButton className="agent-home-menu" aria-label="切换导航" aria-expanded={menuOpen} onClick={() => setMenuOpen(!menuOpen)}><PanelLeft size={20} /></PressButton><span>千岸 Agent</span><span className="agent-home-badge">跨境上新</span></div>
          <Link href="/workbench">查看任务 <ArrowUpRight size={14} /></Link>
        </header>
        <section className="agent-home-start" aria-labelledby="agent-home-title">
          <Enter className="agent-home-intro"><div className="agent-home-mark"><Globe2 size={29} strokeWidth={1.3} /></div><p>让好商品，走向更远的地方</p><h1 id="agent-home-title">今天，想把什么卖向世界？</h1><span>告诉千岸你的商品和目标，把上新交给 Agent。</span></Enter>
          <Enter delay={0.08} className={`agent-home-composer ${dragOver ? "is-dragging" : ""}`} onDragOver={(e) => { e.preventDefault(); setDragOver(true); }} onDragLeave={() => setDragOver(false)} onDrop={(e) => { e.preventDefault(); setDragOver(false); onFile(e.dataTransfer.files?.[0]); }}>
            {preview && <div className="agent-home-attachment"><img src={preview} alt="已上传的商品图" /><span>商品图片</span><PressButton onClick={clearImage} aria-label="移除商品图"><X size={16} /></PressButton></div>}
            <textarea aria-label="描述商品和上新需求" value={sellingPoints} maxLength={2000} onChange={(e) => { setSellingPoints(e.target.value); setProductName(""); }} placeholder="例如：我有一款 380ml 便携榨汁杯，USB-C 充电，帮我准备出海上架内容…" rows={3} disabled={loading} onKeyDown={(e) => { if (e.key === "Enter" && !e.shiftKey && !e.nativeEvent.isComposing) { e.preventDefault(); if (!loading) void submit(); } }} />
            <div className="agent-home-composer-tools">
              <div><PressButton className="agent-home-icon" onClick={() => fileRef.current?.click()} aria-label="上传商品图片" title="上传商品图片"><Plus size={21} /></PressButton><PressButton className="agent-home-settings" onClick={() => setSettingsOpen(!settingsOpen)} aria-expanded={settingsOpen} aria-controls="agent-home-settings"><SlidersHorizontal size={15} /><span>{platforms.length} 个平台</span></PressButton><span className="agent-home-mode"><Sparkles size={13} />Agent</span></div>
              <PressButton className="agent-home-send" onClick={submit} disabled={loading} aria-label={loading ? "创建任务中" : "开始上架任务"}>{loading ? <span className="animate-pulse">•••</span> : <ArrowUp size={20} />}</PressButton>
            </div>
            <input ref={fileRef} type="file" accept="image/*" aria-label="商品图片" className="hidden" onChange={(e) => { onFile(e.target.files?.[0]); e.target.value = ""; }} />
            <Reveal open={settingsOpen} id="agent-home-settings"><div className="agent-home-options"><p>发布到哪些平台？</p><div className="agent-home-platforms">{PLATFORM_META.map((p) => <PressButton key={p.key} aria-pressed={platforms.includes(p.key)} onClick={() => togglePlatform(p.key)}>{p.name}{platforms.includes(p.key) && <span>✓</span>}</PressButton>)}</div><label htmlFor="agent-product-name">商品名称（可选）</label><input id="agent-product-name" maxLength={200} className="field" value={productName} onChange={(e) => setProductName(e.target.value)} placeholder="补充准确的商品名称" /><label htmlFor="agent-request">本次任务</label><input id="agent-request" maxLength={300} className="field" value={requestText} onChange={(e) => setRequestText(e.target.value)} placeholder="默认生成完整上架包，也可以先看方案" /></div></Reveal>
          </Enter>
          {error && <Feedback role="alert" className="mt-3 text-sm text-red-600">{error}</Feedback>}
          <p className="agent-home-hint">上传商品图，或直接描述商品 · Enter 开始，Shift + Enter 换行</p>
          <div className="agent-home-suggestions">{REQUEST_PRESETS.map((p) => <PressButton key={p.label} aria-pressed={requestText === p.text} onClick={() => { setRequestText(p.text); if (p.label === "只要东南亚") setPlatforms(["shopee", "lazada", "tiktokshop"]); }}><span>{p.label === "先看方案" ? "先帮我规划" : p.label === "只要东南亚" ? "拓展东南亚" : "生成完整上架包"}</span><ArrowUpRight size={14} /></PressButton>)}</div>
          {requestText && <p className="agent-home-selection">{requestText}<PressButton aria-label="清除任务偏好" onClick={() => setRequestText("")}><X size={13} /></PressButton></p>}
          <div className="agent-home-examples"><span>没有灵感？从一件商品开始</span><div>{SAMPLES.map((s, i) => <PressButton key={s.name} onClick={() => fillSample(i)}><Package size={15} />{s.name}</PressButton>)}</div></div>
          <div className="agent-home-journey">{LAUNCH_FLOW.map((step, i) => <span key={step.no}>{i > 0 && <span className="agent-home-journey-arrow">→</span>}{step.title}</span>)}</div>
        </section>
        <details className="agent-home-more"><summary>了解千岸能为你做什么 <span>产出物 · 选品灵感 · 平台能力</span></summary>
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
                <PressButton
                  key={m.key}
                  data-on={market === m.key}
                  onClick={() => setMarket(m.key)}
                  className="segment-item"
                >
                  {m.name}
                </PressButton>
              ))}
            </div>
            <div className="segment">
              {IDEA_CATEGORIES.map((c) => (
                <PressButton
                  key={c.key}
                  data-on={ideaCategory === c.key}
                  onClick={() => setIdeaCategory(c.key)}
                  className="segment-item"
                >
                  {c.name}
                </PressButton>
              ))}
            </div>
            <PressButton onClick={genIdeation} disabled={ideaLoading} className="btn-primary !px-4 !py-2 !text-xs">
              {ideaLoading ? "AI 分析中…" : "生成选品建议"}
            </PressButton>
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

        {ideaError && (
          <p role="alert" className="mt-3 text-sm text-red-600">
            {ideaError}
          </p>
        )}

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
                <PressButton
                  onClick={() => useIdea(idea)}
                  className="btn-primary mt-4 !w-full !py-2 !text-xs"
                >
                  上架这个 →
                </PressButton>
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
          <PressButton
            onClick={() => window.scrollTo({ top: 0, behavior: "smooth" })}
            className="mt-6 inline-flex items-center gap-2 rounded-lg bg-white px-6 py-3 text-sm font-semibold text-brand-900 shadow-lg transition hover:bg-brand-50 active:translate-y-px"
          >
            立即创建上架任务 ↑
          </PressButton>
        </div>
      </section>

        </details>
        <Footer />
      </div>
    </main>
  );
}
