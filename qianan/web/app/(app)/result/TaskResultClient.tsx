"use client";

import { useCallback, useState } from "react";
import { useSearchParams } from "next/navigation";
import Nav from "@/components/Nav";
import PublishPanel from "@/components/PublishPanel";
import AgentTracePanel from "@/components/AgentTracePanel";
import AgentCapabilityPanel from "@/components/AgentCapabilityPanel";
import { exportUrl, fetchTask, PLATFORM_META, submitFeedback, validateDraft, zipUrl, type ComplianceIssue, type PlatformListing, type TaskDetail } from "@/lib/api";
import { useTaskPolling } from "@/lib/useTaskPolling";

const STEPS = [
  { label: "商品理解", desc: "读懂商品与卖点，结构化提取" },
  { label: "规则匹配", desc: "查询平台规则库，输出约束清单" },
  { label: "文案生成", desc: "多语言本地化，非直译" },
  { label: "主图生成", desc: "按各平台规范生成主图" },
  { label: "合规体检", desc: "禁用词 / 字符 / 属性逐条校验" },
];

/** 展示用：各平台标题字符上限（仅用于字符计数角标）。 */
const TITLE_LIMITS: Record<string, number> = {
  amazon: 200,
  shopee: 255,
  aliexpress: 128,
  lazada: 255,
  tiktokshop: 255,
};

function stageToIndex(task: TaskDetail): number {
  if (task.status === "done") return STEPS.length;
  const s = task.stage || "";
  if (s.includes("理解")) return 0;
  if (s.includes("规则") || s.includes("匹配")) return 1;
  if (s.includes("文案")) return 2;
  if (s.includes("主图")) return 3;
  if (
    s.includes("合规") ||
    s.includes("自检") ||
    s.includes("自愈") ||
    s.includes("修订") ||
    s.includes("就绪")
  )
    return 4;
  return 0;
}

const platformName = (key: string) => PLATFORM_META.find((p) => p.key === key)?.name || key;
const platformDot = (key: string) => PLATFORM_META.find((p) => p.key === key)?.dot || "#97a6bb";

function allEqual(vals: string[]): boolean {
  return vals.every((v) => v === vals[0]);
}

/** 5 平台并排差异对比（路演视图）：字段存在平台间差异时整行琥珀色高亮，一致则灰显。 */
function CompareSection({ listings }: { listings: PlatformListing[] }) {
  const rows = [
    {
      label: "主语言",
      note: "按目标市场本地化",
      vals: listings.map((l) => l.locales[0] || "—"),
    },
    {
      label: "标题",
      note: "按平台规范自适应长度",
      vals: listings.map((l) => `${l.title.length} 字 · ${l.title.slice(0, 30)}${l.title.length > 30 ? "…" : ""}`),
    },
    {
      label: "五点描述",
      note: "Amazon 专属结构",
      vals: listings.map((l) =>
        l.bullets.length ? `${l.bullets.length} 条 · ${l.bullets[0].slice(0, 22)}…` : "平台不要求"
      ),
    },
    {
      label: "商品描述",
      note: "按平台字数与结构适配",
      vals: listings.map((l) => `${l.description.length} 字 · ${l.description.slice(0, 26)}…`),
    },
    {
      label: "类目属性",
      note: "逐平台字段映射",
      vals: listings.map((l) => `${Object.keys(l.attributes).length} 项`),
    },
    {
      label: "合规体检",
      note: "禁用词 / 字符 / 属性校验",
      vals: listings.map((l) => (l.compliance_passed ? "通过" : "存在风险")),
    },
    {
      label: "自愈修订",
      note: "命中禁用词自动重写",
      vals: listings.map((l) => (l.revised_count ? `修订 ${l.revised_count} 次` : "—")),
    },
    {
      label: "主图",
      note: "各平台独立生成",
      vals: listings.map((l) => l.images[0] || "—"),
    },
  ].map((r) => ({ ...r, differ: !allEqual(r.vals) }));

  const diffCount = rows.filter((r) => r.differ).length;

  return (
    <section className="mt-14 animate-fade-up">
      <div className="flex flex-wrap items-end justify-between gap-2">
        <div>
          <p className="eyebrow">Compare · Spec Sheet</p>
          <h2 className="mt-2 text-2xl font-semibold tracking-tight text-ink-900">平台差异对比</h2>
        </div>
        <span className="font-mono text-[11px] tabular-nums text-ink-400">
          {listings.length} 个平台并排 · {diffCount} 个字段存在差异（琥珀高亮），其余一致
        </span>
      </div>
      <div className="card mt-5 overflow-x-auto">
        <table className="w-full min-w-[900px] border-collapse text-sm">
          <thead>
            <tr className="border-b border-ink-100 text-left">
              <th className="spec-label sticky left-0 z-10 bg-white px-5 py-3.5 font-medium">字段 / Field</th>
              {listings.map((l) => (
                <th key={l.platform} className="px-4 py-3.5">
                  <span className="inline-flex items-center gap-1.5">
                    <span
                      className="h-1.5 w-1.5 rounded-full"
                      style={{ background: platformDot(l.platform) }}
                    />
                    <span className="spec-label !text-ink-600">{l.display_name || platformName(l.platform)}</span>
                  </span>
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {rows.map((row) => (
              <tr key={row.label} className={`border-b border-ink-100 last:border-0 ${row.differ ? "bg-amber-50" : ""}`}>
                <td className={`sticky left-0 z-10 px-5 py-3 ${row.differ ? "bg-amber-50" : "bg-white"}`}>
                  <div className="flex items-center gap-2">
                    <span className={`h-1.5 w-1.5 shrink-0 rounded-full ${row.differ ? "bg-amber-500" : "bg-ink-200"}`} />
                    <div>
                      <p className="font-mono text-xs font-medium text-ink-800">{row.label}</p>
                      <p className="mt-0.5 font-mono text-[10px] text-ink-400">{row.note}</p>
                    </div>
                  </div>
                </td>
                {row.vals.map((v, i) => {
                  const listing = listings[i];
                  const isImage = row.label === "主图";
                  const isCompliance = row.label === "合规体检";
                  return (
                    <td key={listing.platform} className="px-4 py-3 align-top">
                      {isImage ? (
                        v === "—" ? (
                          <span className="text-ink-300">—</span>
                        ) : (
                          // eslint-disable-next-line @next/next/no-img-element
                          <img src={v} alt={`${listing.display_name} 主图`} className="h-10 w-10 rounded-lg object-cover ring-1 ring-ink-100" />
                        )
                      ) : isCompliance ? (
                        <span
                          className={`inline-flex items-center gap-1.5 rounded-full px-2 py-0.5 text-xs font-medium ${
                            v === "通过" ? "bg-green-50 text-green-600" : "bg-red-50 text-red-600"
                          }`}
                        >
                          {v}
                        </span>
                      ) : (
                        <span className={`text-[13px] tabular-nums ${row.differ ? "text-amber-600" : "text-ink-400"}`}>{v}</span>
                      )}
                    </td>
                  );
                })}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <p className="mt-2 text-xs text-ink-400">
        高亮字段说明平台按各自规范做了差异化适配（语言、标题长度、描述结构、属性映射等），保证每岸合规可上架。
      </p>
    </section>
  );
}

/** 某一字段的即时校验问题（基于 /api/audit 编辑态结果）。 */
function FieldIssues({
  field,
  active,
  audits,
}: {
  field: string;
  active: number;
  audits: Record<number, { passed: boolean; issues: ComplianceIssue[] }>;
}) {
  const res = audits[active];
  if (!res) return null;
  const iss = res.issues.filter((i) => i.field === field);
  if (iss.length === 0) return null;
  return (
    <ul className="mt-2 space-y-1.5">
      {iss.map((i, k) => (
        <li
          key={k}
          className={`flex items-start gap-2 rounded-md px-2.5 py-1.5 text-xs leading-5 ${
            i.severity === "error" ? "bg-red-50 text-red-600" : "bg-amber-50 text-amber-600"
          }`}
        >
          <span className="mt-0.5 font-mono text-[10px] font-medium uppercase tracking-[0.06em] opacity-75">{i.check_id}</span>
          <span>
            <span className="font-medium">{i.field}</span> · {i.message}
          </span>
        </li>
      ))}
    </ul>
  );
}

export default function ResultPage() {
  const searchParams = useSearchParams();
  const taskId = searchParams.get("taskId") || "";
  const [task, setTask] = useState<TaskDetail | null>(null);
  const [active, setActive] = useState(0);
  const [feedback, setFeedback] = useState<Record<string, number>>({});

  // ---- F1: 结果页可编辑 + 即时合规校验（复用 /api/audit，确定性规则引擎，不耗额度）----
  const [drafts, setDrafts] = useState<Record<number, { title: string; bullets: string[]; description: string }>>({});
  const [editingMap, setEditingMap] = useState<Record<number, boolean>>({});
  const [audits, setAudits] = useState<Record<number, { passed: boolean; issues: ComplianceIssue[] }>>({});
  const [auditing, setAuditing] = useState<Record<number, boolean>>({});

  const draftOf = (idx: number): { title: string; bullets: string[]; description: string } => {
    const l = task?.listings[idx];
    const saved = drafts[idx];
    return saved ?? { title: l?.title ?? "", bullets: l?.bullets ?? [], description: l?.description ?? "" };
  };

  /** 当前草稿是否与原始文案一致（一致 = 未做任何修改）。 */
  const isDirtyOf = (idx: number): boolean => {
    const l = task?.listings[idx];
    if (!l) return false;
    const d = drafts[idx];
    if (!d) return false;
    return d.title !== l.title || d.description !== l.description || d.bullets.join("\n") !== l.bullets.join("\n");
  };

  /** 放弃修改：草稿与该平台的编辑态校验结果一并清空，回到原文案。 */
  const discardDraft = (idx: number) => {
    setDrafts((p) => {
      const n = { ...p };
      delete n[idx];
      return n;
    });
    setAudits((p) => {
      const n = { ...p };
      delete n[idx];
      return n;
    });
  };

  const runAudit = useCallback(
    async (idx: number) => {
      const l = task?.listings[idx];
      if (!l) return;
      const d = drafts[idx] ?? { title: l.title, bullets: l.bullets, description: l.description };
      const category = (task?.request as { category?: string } | undefined)?.category || "home_kitchen";
      setAuditing((a) => ({ ...a, [idx]: true }));
      try {
        const res = await validateDraft({
          platform: l.platform,
          category,
          title: d.title,
          bullets: d.bullets,
          description: d.description,
          attributes: l.attributes,
          images: l.images,
        });
        setAudits((prev) => ({ ...prev, [idx]: { passed: res.passed, issues: res.issues } }));
      } catch {
        /* 校验失败不阻断编辑 */
      } finally {
        setAuditing((a) => ({ ...a, [idx]: false }));
      }
    },
    [drafts, task]
  );

  // 任务轮询：1.5s 一轮直至 done / failed；失败退避（首次失败 3s，随后指数递增），
  // 连续 20 次失败即停止并提示，避免后端不可达时无限重试。
  const [pollError, setPollError] = useState("");
  useTaskPolling({
    fetchFn: () => fetchTask(taskId),
    interval: 1500,
    backoff: "exponential",
    maxAttempts: 20,
    enabled: !!taskId,
    isDone: (detail) => detail.status === "done" || detail.status === "failed",
    onUpdate: setTask,
    onError: (e, gaveUp) => {
      if (gaveUp) setPollError(String(e));
    },
  });

  if (!task) {
    return (
      <main className="pb-24">
        <Nav />
        <div className="mx-auto max-w-3xl px-6 py-24 text-center">
          {pollError ? (
            <>
              <p className="eyebrow !text-red-500">Connection Error</p>
              <p className="mt-4 text-lg text-red-600">无法连接后端：{pollError}</p>
              <p className="mt-2 text-sm text-ink-400">请确认后端已启动后刷新页面重试</p>
            </>
          ) : (
            <>
              <span className="inline-block h-2 w-2 animate-pulse-dot rounded-full bg-brand-600" />
              <p className="eyebrow mt-4">Loading · 加载中…</p>
            </>
          )}
        </div>
      </main>
    );
  }

  if (task.status === "failed") {
    return (
      <main className="pb-24">
        <Nav />
        <div className="mx-auto max-w-3xl px-6 py-24 text-center">
          <p className="eyebrow !text-red-500">Task Failed</p>
          <p className="mt-4 text-lg text-red-600">生成失败：{task.error}</p>
          <a href="/" className="btn-primary mt-8 inline-flex">
            返回重试
          </a>
        </div>
      </main>
    );
  }

  /* ---------- 阶段一：流水线 ---------- */
  if (task.status !== "done") {
    const idx = stageToIndex(task);
    const kw = task.understanding?.keywords || [];
    return (
      <main className="pb-24">
        <Nav />
        <section className="contour-bg relative overflow-hidden">
          <div className="mx-auto max-w-6xl px-6 py-16">
            <div className="flex items-center gap-2.5 animate-fade-up">
              <span className="h-2 w-2 animate-pulse-dot rounded-full bg-brand-300" />
              <p className="eyebrow !text-brand-300">Generating · 上架流水线运转中</p>
            </div>
            <h1 className="mt-4 text-3xl font-semibold tracking-tight text-white sm:text-4xl">
              正在生成上架包…
            </h1>
            <p className="mt-2 text-sm text-brand-100/70">{task.request?.product_name}</p>

            {/* 工作台两栏：左侧五阶段进度 · 右侧 Agent 实时动态 */}
            <div className="mt-12 grid gap-10 lg:grid-cols-[minmax(0,1fr)_380px] lg:items-start">
            <div className="min-w-0">
            {/* 五阶段进度 */}
            <div>
              {STEPS.map((step, i) => {
                const isDone = i < idx;
                const isActive = i === idx;
                return (
                  <div key={step.label} className="flex gap-4">
                    {/* 竖线 + 圆点 */}
                    <div className="flex flex-col items-center">
                      <span
                        className={`flex h-7 w-7 items-center justify-center rounded-full font-mono text-[11px] font-medium transition duration-150 ${
                          isDone
                            ? "bg-green-500 text-white"
                            : isActive
                              ? "border border-brand-300 bg-brand-300/15 text-brand-100"
                              : "border border-white/15 text-brand-200/40"
                        }`}
                      >
                        {isDone ? "✓" : String(i + 1).padStart(2, "0")}
                      </span>
                      {i < STEPS.length - 1 && (
                        <span className={`my-1 w-px flex-1 ${isDone ? "bg-green-500/50" : "bg-white/10"}`} />
                      )}
                    </div>
                    {/* 内容 */}
                    <div className={`flex-1 pb-7 transition duration-150 ${isDone || isActive ? "" : "opacity-40"}`}>
                      <div className="flex items-center justify-between gap-3">
                        <p className="font-mono text-[10px] font-medium uppercase tracking-[0.08em] text-brand-300/70">
                          Step {String(i + 1).padStart(2, "0")}
                        </p>
                        {isActive && (
                          <span className="flex items-center gap-1.5 font-mono text-[10px] uppercase tracking-[0.08em] text-brand-300">
                            <span className="h-1.5 w-1.5 animate-pulse-dot rounded-full bg-brand-300" />
                            Running
                          </span>
                        )}
                        {isDone && (
                          <span className="font-mono text-[10px] uppercase tracking-[0.08em] text-green-400">
                            Done
                          </span>
                        )}
                      </div>
                      <p className={`mt-1 text-sm font-medium ${isDone || isActive ? "text-white" : "text-brand-200/50"}`}>
                        {step.label}
                      </p>
                      <p className="mt-0.5 text-xs text-brand-100/50">{step.desc}</p>

                      {/* 中间产物：商品理解完成后的关键词 */}
                      {i === 0 && kw.length > 0 && (
                        <div className="mt-2 flex flex-wrap gap-1.5">
                          {kw.slice(0, 6).map((k) => (
                            <span
                              key={k}
                              className="rounded-md border border-white/15 bg-white/5 px-2 py-0.5 font-mono text-[11px] text-brand-100"
                            >
                              {k}
                            </span>
                          ))}
                        </div>
                      )}
                      {/* 中间产物：当前正在进行的子阶段 */}
                      {isActive && (
                        <p className="mt-2 font-mono text-[11px] text-brand-200">{task.stage}</p>
                      )}
                    </div>
                  </div>
                );
              })}
            </div>

            {/* 细进度条 */}
            <div className="mt-2">
              <div className="h-1 overflow-hidden rounded-full bg-white/10">
                <div
                  className="h-full rounded-full bg-brand-300 transition-all duration-700"
                  style={{ width: `${Math.round(task.progress * 100)}%` }}
                />
              </div>
              <div className="mt-2 flex items-center justify-between font-mono text-[11px] tabular-nums text-brand-200/70">
                <span className="uppercase tracking-[0.08em]">Progress</span>
                <span>{Math.round(task.progress * 100)}%</span>
              </div>
              {pollError && (
                <p className="mt-3 rounded-lg bg-red-500/10 px-3 py-2 text-xs leading-5 text-red-300">
                  后端连接持续失败，已暂停进度刷新：{pollError} —— 请确认后端已启动，刷新页面可继续跟踪
                </p>
              )}
            </div>
            </div>
            <aside className="lg:sticky lg:top-8">
              <AgentTracePanel events={task.trace || []} running variant="dark" />
            </aside>
            </div>
          </div>
        </section>
      </main>
    );
  }

  /* ---------- 阶段二：结果展示 ---------- */
  const listings = task.listings;
  const current: PlatformListing | undefined = listings[active];
  const liveAudit = audits[active];
  const editing = !!editingMap[active];
  const isDirty = isDirtyOf(active);
  const errCount = liveAudit ? liveAudit.issues.filter((i) => i.severity === "error").length : 0;
  const warnCount = liveAudit ? liveAudit.issues.length - errCount : 0;
  const passedCount = listings.filter((l) => l.compliance_passed).length;
  const revisedTotal = listings.reduce((n, l) => n + (l.revised_count || 0), 0);

  /** 拉取导出包，把当前平台的后台导入 CSV 下载到本地（Excel 直开）。 */
  async function downloadImportFile(platform: string) {
    if (!taskId) return;
    const res = await fetch(exportUrl(taskId));
    const data = await res.json();
    const listing = (data.listings as PlatformListing[]).find((l) => l.platform === platform);
    const files = listing?.import_files;
    if (!files) return;
    for (const [name, content] of Object.entries(files)) {
      const blob = new Blob(["" + content], { type: "text/csv;charset=utf-8" });
      const a = document.createElement("a");
      a.href = URL.createObjectURL(blob);
      a.download = name;
      a.click();
      URL.revokeObjectURL(a.href);
    }
  }

  /** 人对上架包打分：喂给 Agent 记忆库与进化分析（差评可附原因进反思）。 */
  async function onRate(rating: number) {
    if (!current || !taskId) return;
    let comment = "";
    if (rating === -1) {
      const c = window.prompt("哪里不满意？（可选，将进入 Agent 反思）");
      if (c === null) return;
      comment = c;
    }
    try {
      await submitFeedback(taskId, current.platform, rating, comment);
      setFeedback((f) => ({ ...f, [current.platform]: rating }));
    } catch (e) {
      alert(`反馈提交失败：${String(e)}`);
    }
  }

  return (
    <main className="pb-24">
      <Nav />

      {/* ---------- Hero：上架包头部 ---------- */}
      <section className="contour-bg relative overflow-hidden">
        <div className="mx-auto max-w-6xl px-6 pb-20 pt-14">
          <p className="eyebrow !text-brand-300 animate-fade-up">Listing Package · 上架包</p>
          <h1 className="mt-4 max-w-3xl text-[32px] font-semibold leading-[1.2] tracking-tight text-white sm:text-4xl">
            {task.request?.product_name || "上架包已生成"}
          </h1>

          {/* mono 任务元信息 */}
          <div className="mt-6 flex flex-wrap items-center gap-x-6 gap-y-2">
            <span className="font-mono text-[11px] uppercase tracking-[0.08em] tabular-nums text-brand-200">
              Task {task.task_id}
            </span>
            <span className="font-mono text-[11px] uppercase tracking-[0.08em] tabular-nums text-brand-200">
              Platforms {listings.length}
            </span>
            <span className="font-mono text-[11px] uppercase tracking-[0.08em] tabular-nums text-brand-200">
              Compliance {passedCount}/{listings.length}
            </span>
            <span className="font-mono text-[11px] uppercase tracking-[0.08em] tabular-nums text-brand-200">
              Self-Heal ×{revisedTotal}
            </span>
          </div>

          {/* 操作按钮组 */}
          <div className="mt-9 flex flex-wrap gap-3">
            <a
              href={zipUrl(task.task_id)}
              className="inline-flex items-center justify-center gap-2 rounded-lg bg-white px-5 py-2.5 text-sm font-medium text-brand-900 shadow-sm transition duration-150 hover:bg-brand-100 active:translate-y-px"
            >
              整包下载 ZIP
            </a>
            <a
              href={exportUrl(task.task_id)}
              target="_blank"
              className="inline-flex items-center justify-center gap-2 rounded-lg border border-white/25 px-5 py-2.5 text-sm font-medium text-white transition duration-150 hover:border-white/50 hover:bg-white/5 active:translate-y-px"
            >
              导出 JSON
            </a>
            <a
              href="/"
              className="inline-flex items-center justify-center gap-2 rounded-lg border border-white/25 px-5 py-2.5 text-sm font-medium text-white transition duration-150 hover:border-white/50 hover:bg-white/5 active:translate-y-px"
            >
              再来一稿
            </a>
          </div>
        </div>
        {/* 底部渐变过渡 */}
        <div className="pointer-events-none absolute inset-x-0 bottom-0 h-16 bg-gradient-to-b from-transparent to-[#f2f5fb]" />
      </section>

      <div className="mx-auto max-w-6xl px-6">
        {/* ---------- Agent 能力证据面板（全宽，评委第一眼看到四项 Agentic 能力） ---------- */}
        <div className="mt-8 animate-fade-up">
          <AgentCapabilityPanel task={task} />
        </div>

        {/* ---------- 闭环总览：把“生成完成”明确连接到下一步发布 ---------- */}
        <section className="card mt-5 overflow-hidden animate-fade-up">
          <div className="flex flex-wrap items-center justify-between gap-3 border-b border-ink-100 px-5 py-4">
            <div>
              <p className="eyebrow">Launch Control · 下一步</p>
              <p className="mt-1 text-sm font-medium text-ink-900">上架包已就绪，选择平台后即可执行发布</p>
            </div>
            <span className="rounded-full bg-green-50 px-2.5 py-1 font-mono text-[10px] font-medium text-green-600">
              {passedCount}/{listings.length} 平台合规通过
            </span>
          </div>
          <div className="grid divide-y divide-ink-100 sm:grid-cols-3 sm:divide-x sm:divide-y-0">
            <div className="px-5 py-4">
              <p className="spec-label">01 · REVIEW</p>
              <p className="mt-1.5 text-xs leading-5 text-ink-500">先查看当前平台的文案、主图与字段证据，必要时编辑并重新校验。</p>
            </div>
            <div className="px-5 py-4">
              <p className="spec-label">02 · PUBLISH</p>
              <p className="mt-1.5 text-xs leading-5 text-ink-500">在右侧“自动上架”卡片确认后执行，过程会记录每一步和后台截图。</p>
            </div>
            <div className="px-5 py-4">
              <p className="spec-label">03 · RECEIPT</p>
              <p className="mt-1.5 text-xs leading-5 text-ink-500">成功返回 Listing ID 与链接；失败会保留错误原因，支持修复后再次提交。</p>
            </div>
          </div>
        </section>

        {/* 工作台两栏：左内容 · 右 Agent 轨迹 */}
        <div className="grid gap-10 xl:grid-cols-[minmax(0,1fr)_320px] xl:items-start">
        <div className="min-w-0">
        {/* 平台 Tab */}
        <div className="mt-8 flex flex-wrap gap-2 animate-fade-up">
          {listings.map((l, i) => {
            const on = i === active;
            return (
              <button
                key={l.platform}
                onClick={() => setActive(i)}
                className={`flex items-center gap-2 rounded-lg border px-3.5 py-2 text-[13px] transition duration-150 ${
                  on
                    ? "border-brand-800 bg-brand-800 font-medium text-white shadow-sm"
                    : "border-ink-200 bg-white text-ink-600 hover:border-ink-300 hover:text-ink-800"
                }`}
              >
                <span
                  className="h-1.5 w-1.5 rounded-full"
                  style={{ background: platformDot(l.platform) }}
                />
                {l.display_name || platformName(l.platform)}
                <span className={`h-1.5 w-1.5 rounded-full ${l.compliance_passed ? "bg-green-500" : "bg-red-500"}`} />
              </button>
            );
          })}
        </div>

        {/* ---------- 当前平台上架包（主图 + 文案 + 合规，单平台详情先行） ---------- */}
        {current && (
          <div className="mt-8 animate-fade-up">
            <div className="flex flex-wrap items-end justify-between gap-2">
              <div>
                <p className="eyebrow">Current Package · 当前平台</p>
                <h2 className="mt-2 text-2xl font-semibold tracking-tight text-ink-900">
                  {current.display_name || platformName(current.platform)} 上架包
                </h2>
              </div>
              <span className="font-mono text-[11px] text-ink-400">
                {active + 1}/{listings.length} PLATFORMS · 切换上方标签查看其余平台
              </span>
            </div>
          </div>
        )}

        {current && (
          <div className="mt-5 grid gap-6 lg:grid-cols-[3fr_2fr] animate-fade-up">
            {/* 左：文案内容（只读 / 编辑双态，编辑态支持即时合规校验） */}
            <section className="card p-7">
              {/* 卡片头：编辑 toggle / 编辑态操作按钮 */}
              <div className="mb-4 flex flex-wrap items-center justify-between gap-2">
                <h2 className="eyebrow">Listing Copy · 文案</h2>
                {editing ? (
                  <div className="flex items-center gap-2">
                    <button
                      onClick={() => runAudit(active)}
                      disabled={auditing[active]}
                      className="rounded-md bg-brand-800 px-2.5 py-1 text-xs font-medium text-white transition duration-150 hover:bg-brand-700 disabled:cursor-not-allowed disabled:opacity-60"
                    >
                      {auditing[active] ? "校验中…" : "合规校验"}
                    </button>
                    <button
                      onClick={() => discardDraft(active)}
                      disabled={!isDirty && !audits[active]}
                      className="rounded-md border border-ink-200 bg-white px-2.5 py-1 text-xs text-ink-600 transition duration-150 hover:border-ink-300 hover:text-ink-800 disabled:cursor-not-allowed disabled:opacity-50"
                    >
                      放弃修改
                    </button>
                    <button
                      onClick={() => setEditingMap((p) => ({ ...p, [active]: false }))}
                      className="rounded-md border border-ink-200 bg-white px-2.5 py-1 text-xs text-ink-600 transition duration-150 hover:border-ink-300 hover:text-ink-800"
                    >
                      完成
                    </button>
                  </div>
                ) : (
                  <button
                    onClick={() => setEditingMap((p) => ({ ...p, [active]: true }))}
                    className="rounded-md border border-ink-200 bg-white px-2.5 py-1 text-xs text-ink-600 transition duration-150 hover:border-ink-300 hover:text-ink-800"
                  >
                    编辑
                  </button>
                )}
              </div>

              {/* 校验结果汇总横幅 / 编辑提示 */}
              {liveAudit ? (
                <div
                  className={`mb-4 rounded-lg px-3 py-2 ring-1 ${
                    errCount > 0 ? "bg-red-50 ring-red-100" : "bg-green-50 ring-green-100"
                  }`}
                >
                  <span className={`text-xs font-medium ${errCount > 0 ? "text-red-600" : "text-green-600"}`}>
                    {errCount > 0 ? `未通过 · ${errCount} 项 error` : `通过合规校验 · ${warnCount} 项提示`}
                  </span>
                  {warnCount > 0 && errCount > 0 && (
                    <span className="ml-2 text-xs text-amber-600">另有 {warnCount} 项提示</span>
                  )}
                </div>
              ) : editing ? (
                <div className="mb-4 rounded-lg bg-brand-50 px-3 py-2 ring-1 ring-brand-100">
                  <span className="text-xs text-brand-700">
                    编辑中 · 修改后点击「合规校验」，问题会就地显示在对应字段下方（不耗额度）
                  </span>
                </div>
              ) : null}

              {/* 已恢复原文案提示 */}
              {editing && !isDirty && (
                <p className="mb-4 font-mono text-[11px] text-ink-400">已恢复原文案</p>
              )}

              {/* 标题 */}
              <div>
                <div className="flex items-baseline justify-between gap-3">
                  <h2 className="eyebrow">标题 · {current.locales.join(" / ")}</h2>
                  <span className="font-mono text-[11px] tabular-nums text-ink-400">
                    {draftOf(active).title.length}/{TITLE_LIMITS[current.platform] || 200}
                  </span>
                </div>
                {editing ? (
                  <input
                    value={draftOf(active).title}
                    onChange={(e) => {
                      setDrafts((p) => ({
                        ...p,
                        [active]: { ...(p[active] ?? { title: current.title, bullets: current.bullets, description: current.description }), title: e.target.value },
                      }));
                      setAudits((p) => { const n = { ...p }; delete n[active]; return n; });
                    }}
                    className="mt-3 w-full rounded-lg border border-ink-200 bg-white px-3 py-2 text-base font-medium leading-7 text-ink-900 outline-none transition focus:border-brand-500 focus:ring-2 focus:ring-brand-100"
                  />
                ) : (
                  <p className="mt-3 text-base font-medium leading-7 text-ink-900">{draftOf(active).title}</p>
                )}
                <FieldIssues field="title" active={active} audits={audits} />
              </div>

              {/* 五点描述 */}
              {current.bullets.length > 0 && (
                <div className="mt-6 border-t border-ink-100 pt-6">
                  <div className="flex items-baseline justify-between gap-3">
                    <h2 className="eyebrow">五点描述</h2>
                    <span className="font-mono text-[11px] tabular-nums text-ink-400">
                      {draftOf(active).bullets.length} 条
                    </span>
                  </div>
                  <ul className="mt-3 space-y-2">
                    {draftOf(active).bullets.map((b, i) => (
                      <li key={i} className="flex gap-2.5">
                        <span className="mt-2 font-mono text-[10px] font-medium tabular-nums text-brand-400">
                          {String(i + 1).padStart(2, "0")}
                        </span>
                        {editing ? (
                          <textarea
                            value={b}
                            onChange={(e) => {
                              setDrafts((p) => {
                                const base = p[active] ?? { title: current.title, bullets: current.bullets, description: current.description };
                                const nb = [...base.bullets];
                                nb[i] = e.target.value;
                                return { ...p, [active]: { ...base, bullets: nb } };
                              });
                              setAudits((p) => { const n = { ...p }; delete n[active]; return n; });
                            }}
                            rows={2}
                            className="flex-1 resize-y rounded-lg border border-ink-200 bg-white px-3 py-2 text-sm leading-6 text-ink-600 outline-none transition focus:border-brand-500 focus:ring-2 focus:ring-brand-100"
                          />
                        ) : (
                          <p className="flex-1 text-sm leading-6 text-ink-600">{b}</p>
                        )}
                      </li>
                    ))}
                  </ul>
                  <FieldIssues field="bullets" active={active} audits={audits} />
                </div>
              )}

              {/* 商品描述 */}
              <div className="mt-6 border-t border-ink-100 pt-6">
                <div className="flex items-baseline justify-between gap-3">
                  <h2 className="eyebrow">商品描述</h2>
                  <span className="font-mono text-[11px] tabular-nums text-ink-400">
                    {draftOf(active).description.length} 字
                  </span>
                </div>
                {editing ? (
                  <textarea
                    value={draftOf(active).description}
                    onChange={(e) => {
                      setDrafts((p) => ({
                        ...p,
                        [active]: { ...(p[active] ?? { title: current.title, bullets: current.bullets, description: current.description }), description: e.target.value },
                      }));
                      setAudits((p) => { const n = { ...p }; delete n[active]; return n; });
                    }}
                    rows={6}
                    className="mt-3 w-full resize-y whitespace-pre-wrap rounded-lg border border-ink-200 bg-white px-3 py-2 text-sm leading-6 text-ink-600 outline-none transition focus:border-brand-500 focus:ring-2 focus:ring-brand-100"
                  />
                ) : (
                  <p className="mt-3 whitespace-pre-wrap text-sm leading-6 text-ink-600">{draftOf(active).description}</p>
                )}
                <FieldIssues field="description" active={active} audits={audits} />
              </div>

              <div className="mt-6 border-t border-ink-100 pt-6">
                <h2 className="eyebrow">后台导入表</h2>
                <button
                  onClick={() => downloadImportFile(current.platform)}
                  className="btn-ghost mt-3"
                >
                  下载 {current.display_name || current.platform} 导入 CSV
                </button>
                <p className="mt-2 text-xs text-ink-400">
                  Amazon Flat File / Shopee 批量上传模板列子集，Excel 直开
                </p>
              </div>

              {Object.keys(current.attributes).length > 0 && (
                <div className="mt-6 border-t border-ink-100 pt-6">
                  <div className="flex items-baseline justify-between gap-3">
                    <h2 className="eyebrow">类目属性</h2>
                    <span className="font-mono text-[11px] tabular-nums text-ink-400">
                      {Object.keys(current.attributes).length} 项
                    </span>
                  </div>
                  <div className="mt-3 flex flex-wrap gap-1.5">
                    {Object.entries(current.attributes).map(([k, v]) => (
                      <span key={k} className="rounded-md bg-ink-50 px-2 py-1 font-mono text-[11px] text-ink-600 ring-1 ring-ink-100">
                        {k}: {v}
                      </span>
                    ))}
                  </div>
                </div>
              )}
            </section>

            {/* 右：自动上架 + 主图 + 合规报告 */}
            <aside className="space-y-6">
              {isDirty && (
                <div className="rounded-xl border border-amber-200 bg-amber-50 px-4 py-3 text-xs leading-5 text-amber-700">
                  当前平台有未保存修改。请先完成编辑并重新合规校验；为避免旧版本误发，自动上架暂时锁定。
                </div>
              )}
              <PublishPanel
                taskId={task.task_id}
                platform={current.platform}
                // 编辑态草稿目前只存在于本页；未保存版本禁止发布，避免把旧文案误发到后台。
                compliancePassed={!isDirty && current.compliance_passed}
              />
              <div className="card p-6">
                <div className="flex items-baseline justify-between">
                  <h2 className="eyebrow">主图</h2>
                  <span className="spec-label">Main Image</span>
                </div>
                <div className="mt-4">
                  {current.images.length ? (
                    current.images.map((src) =>
                      src.startsWith("mock://") ? (
                        <div
                          key={src}
                          className="flex aspect-square items-center justify-center rounded-xl bg-ink-50 ring-1 ring-ink-100"
                        >
                          <div className="text-center">
                            <p className="font-mono text-[11px] uppercase tracking-[0.08em] text-ink-300">
                              Image Pending
                            </p>
                            <p className="mt-1.5 text-sm text-ink-400">Mock 主图（接入百炼后生成）</p>
                          </div>
                        </div>
                      ) : (
                        // eslint-disable-next-line @next/next/no-img-element
                        <img key={src} src={src} alt="生成主图" className="aspect-square w-full rounded-xl object-cover ring-1 ring-ink-100" />
                      )
                    )
                  ) : (
                    <div className="flex aspect-square items-center justify-center rounded-xl bg-ink-50 ring-1 ring-ink-100">
                      <p className="text-sm text-ink-400">未生成主图</p>
                    </div>
                  )}
                </div>
              </div>

              <div className="card p-6">
                <div className="flex items-center justify-between">
                  <h2 className="eyebrow">合规报告{liveAudit ? " · 编辑态" : ""}</h2>
                  <span
                    className={`inline-flex items-center gap-1.5 rounded-full px-2.5 py-1 text-xs font-medium ${
                      (liveAudit ? liveAudit.passed : current.compliance_passed) ? "bg-green-50 text-green-600" : "bg-red-50 text-red-600"
                    }`}
                  >
                    {(liveAudit ? liveAudit.passed : current.compliance_passed) ? "✓ 通过" : "存在风险"}
                  </span>
                </div>

                {/* 自愈留痕 */}
                {current.revised_count ? (
                  <div className="mt-3">
                    <span className="inline-flex items-center gap-1.5 rounded-full bg-brand-50 px-2.5 py-1 font-mono text-[11px] font-medium tabular-nums text-brand-700 ring-1 ring-brand-100">
                      <span className="h-1.5 w-1.5 rounded-full bg-brand-500" />
                      已自动修订 {current.revised_count} 次
                    </span>
                  </div>
                ) : null}

                <ul className="mt-4 space-y-2">
                  {((liveAudit ? liveAudit.issues : current.compliance).length === 0) && (
                    <li className="flex items-center gap-2 rounded-lg bg-green-50 px-3 py-2 text-xs text-green-600">
                      <span className="font-medium">✓</span> 无合规提示
                    </li>
                  )}
                  {(liveAudit ? liveAudit.issues : current.compliance).map((issue, i) => (
                    <li
                      key={i}
                      className={`rounded-lg px-3 py-2 text-xs leading-5 ${
                        issue.severity === "error" ? "bg-red-50 text-red-600" : "bg-amber-50 text-amber-600"
                      }`}
                    >
                      <span className="font-mono text-[10px] font-medium uppercase tracking-[0.06em] opacity-75">
                        {issue.check_id}
                      </span>
                      <p className="mt-0.5">
                        <span className="font-medium">{issue.field}</span> · {issue.message}
                      </p>
                    </li>
                  ))}
                </ul>
                <div className="mt-4 flex flex-wrap items-center gap-2 border-t border-ink-100 pt-3">
                  <span className="text-xs text-ink-400">这版上架包质量如何？</span>
                  {feedback[current.platform] ? (
                    <span className="text-xs font-medium text-green-600">已反馈，谢谢</span>
                  ) : (
                    <span className="flex gap-1.5">
                      <button
                        onClick={() => onRate(1)}
                        className="rounded-md border border-ink-200 bg-white px-2.5 py-1 text-xs text-ink-500 shadow-xs transition duration-150 hover:border-green-300 hover:text-green-600"
                      >
                        好评
                      </button>
                      <button
                        onClick={() => onRate(-1)}
                        className="rounded-md border border-ink-200 bg-white px-2.5 py-1 text-xs text-ink-500 shadow-xs transition duration-150 hover:border-red-300 hover:text-red-500"
                      >
                        差评
                      </button>
                    </span>
                  )}
                  <span className="ml-auto font-mono text-[10px] text-ink-300">反馈进入 Agent 记忆</span>
                </div>
              </div>
            </aside>
          </div>
        )}

        {/* ---------- 平台差异对比（单平台详情之后，作为横向核对视图） ---------- */}
        <CompareSection listings={listings} />

        {/* A+ 详情页预览 */}
        {current && current.aplus && current.aplus.length > 0 && (
          <section className="mt-14 animate-fade-up">
            <div className="flex flex-wrap items-end justify-between gap-2">
              <div>
                <p className="eyebrow">A+ Content · 详情页</p>
                <h2 className="mt-2 font-display text-2xl font-semibold tracking-tight text-ink-900">
                  A+ 详情页预览
                </h2>
              </div>
              <span className="font-mono text-[11px] text-ink-400">
                {current.display_name || current.platform} · {current.locales[0] || ""}
              </span>
            </div>

            <div className="mt-5 space-y-4">
              {current.aplus.map((mod, i) => {
                if (mod.type === "headline") {
                  return (
                    <div
                      key={i}
                      className="contour-bg overflow-hidden rounded-2xl px-8 py-14 text-center"
                    >
                      <p className="font-display text-2xl font-semibold tracking-tight text-white sm:text-3xl">{mod.title}</p>
                      {mod.text && <p className="mx-auto mt-3 max-w-md text-sm leading-6 text-brand-100/80">{mod.text}</p>}
                    </div>
                  );
                }
                if (mod.type === "grid") {
                  return (
                    <div key={i} className="card p-7">
                      <h3 className="font-display text-base font-semibold text-ink-900">{mod.title}</h3>
                      <div className="mt-4 grid gap-4 sm:grid-cols-3">
                        {mod.items.map((it, j) => (
                          <div key={j} className="rounded-xl bg-ink-50 p-4 ring-1 ring-ink-100">
                            <p className="text-sm font-medium text-ink-900">{it.title}</p>
                            <p className="mt-1.5 text-xs leading-5 text-ink-500">{it.text}</p>
                          </div>
                        ))}
                      </div>
                    </div>
                  );
                }
                if (mod.type === "compare") {
                  return (
                    <div key={i} className="card p-7">
                      <h3 className="font-display text-base font-semibold text-ink-900">{mod.title}</h3>
                      <div className="mt-3 divide-y divide-ink-100">
                        {mod.items.map((it, j) => (
                          <div key={j} className="flex items-center justify-between py-2.5 text-sm">
                            <span className="font-mono text-xs uppercase tracking-[0.06em] text-ink-400">{it.label}</span>
                            <span className="font-medium tabular-nums text-ink-800">{it.value}</span>
                          </div>
                        ))}
                      </div>
                    </div>
                  );
                }
                if (mod.type === "story") {
                  return (
                    <div key={i} className="rounded-2xl bg-ink-50 px-8 py-12 text-center ring-1 ring-ink-100">
                      <h3 className="font-display text-base font-semibold text-ink-900">{mod.title}</h3>
                      <p className="mx-auto mt-3 max-w-lg text-sm leading-6 text-ink-500">{mod.text}</p>
                    </div>
                  );
                }
                return null;
              })}
            </div>
          </section>
        )}
        </div>
        <aside className="hidden xl:block">
          <div className="sticky top-6">
            <AgentTracePanel events={task.trace || []} variant="light" />
          </div>
        </aside>
        </div>
      </div>
    </main>
  );
}
