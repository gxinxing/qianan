"use client";

import { useCallback, useEffect, useState } from "react";
import Nav from "@/components/Nav";
import {
  decideProposal,
  evolveNow,
  fetchAgentOverview,
  fetchProposals,
  fetchSkillRegistry,
  installSkill,
  uninstallSkill,
  PLATFORM_META,
  type AgentOverview,
  type EvolutionProposal,
  type SkillRegistryEntry,
} from "@/lib/api";

const platformName = (key: string) => PLATFORM_META.find((p) => p.key === key)?.name || key;
const fmtTime = (ts: number) =>
  ts ? new Date(ts * 1000).toLocaleString("zh-CN", { month: "2-digit", day: "2-digit", hour: "2-digit", minute: "2-digit" }) : "—";

const STATUS_META: Record<string, { label: string; cls: string }> = {
  pending: { label: "待审批", cls: "bg-amber-50 text-amber-600" },
  applied: { label: "已生效", cls: "bg-green-50 text-green-700" },
  rejected: { label: "已驳回", cls: "bg-ink-100 text-ink-500" },
  rolled_back: { label: "已回滚", cls: "bg-brand-50 text-brand-700" },
};

const TOOL_TYPE_META: Record<string, { label: string; cls: string }> = {
  http: { label: "HTTP · 实时数据", cls: "bg-green-50 text-green-700" },
  static: { label: "STATIC · 演示数据", cls: "bg-ink-100 text-ink-500" },
  prompt: { label: "PROMPT", cls: "bg-brand-50 text-brand-700" },
};

function changeBrief(p: EvolutionProposal): string {
  if (p.type === "prompt_patch") return `提示词追加：${String(p.change.append || "")}`;
  const words = Array.isArray(p.change.words) ? (p.change.words as string[]).join("、") : "";
  return `规则禁词（${String(p.change.group || "")} 组）：${words}`;
}

export default function AgentPage() {
  const [overview, setOverview] = useState<AgentOverview | null>(null);
  const [registry, setRegistry] = useState<SkillRegistryEntry[]>([]);
  const [proposals, setProposals] = useState<EvolutionProposal[]>([]);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState("");
  const [notice, setNotice] = useState("");
  const [error, setError] = useState("");

  const load = useCallback(async () => {
    try {
      const [ov, reg, props] = await Promise.all([fetchAgentOverview(), fetchSkillRegistry(), fetchProposals()]);
      setOverview(ov);
      setRegistry(reg.registry);
      setProposals(props.proposals);
      setError("");
    } catch (e) {
      setError(`Agent 数据加载失败：${String(e)}`);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  const act = async (label: string, fn: () => Promise<unknown>) => {
    setBusy(label);
    setNotice("");
    try {
      await fn();
      await load();
    } catch (e) {
      setNotice(`操作失败：${String(e)}`);
    } finally {
      setBusy("");
    }
  };

  const pending = proposals.filter((p) => p.status === "pending");
  const history = proposals.filter((p) => p.status !== "pending");
  const trend = overview?.metrics.heal_trend || [];
  const maxRate = Math.max(0.001, ...trend.map((t) => t.heal_rate));
  const connectors = registry.filter((s) => s.kind === "connector");
  const skills = registry.filter((s) => s.kind !== "connector");

  const renderStoreItem = (s: SkillRegistryEntry, isConnector: boolean) => {
    const installed = overview?.skills.find((x) => x.id === s.id);
    return (
      <div key={s.id} className="flex items-start gap-3 rounded-lg p-4 ring-1 ring-ink-100 transition duration-150 hover:bg-ink-50">
        <div className="min-w-0 flex-1">
          <div className="flex flex-wrap items-center gap-2">
            <span className="text-sm font-medium text-ink-800">{s.name}</span>
            <span className="font-mono text-[11px] tabular-nums text-ink-400">v{s.version}</span>
            {installed && isConnector && (
              <span className="flex items-center gap-1.5 rounded-md bg-green-50 px-2 py-0.5 text-xs font-medium text-green-700">
                <span className="inline-block h-1.5 w-1.5 animate-pulse-dot rounded-full bg-green-500" />
                已点亮
              </span>
            )}
            {installed && !isConnector && (
              <span className="rounded-md bg-green-50 px-2 py-0.5 text-xs font-medium text-green-700">已安装</span>
            )}
          </div>
          <p className="mt-1 text-xs leading-5 text-ink-500">{s.description}</p>
          {installed && installed.tools.length > 0 && (
            <p className="mt-1.5 flex flex-wrap items-center gap-1.5 text-[11px] text-ink-400">
              {installed.tools.map((t) => {
                const meta = TOOL_TYPE_META[t.type || "prompt"] || TOOL_TYPE_META.prompt;
                return (
                  <span key={t.name} className="flex items-center gap-1 rounded-md ring-1 ring-ink-100 px-1.5 py-0.5">
                    <span className={`rounded px-1 font-mono text-[10px] ${meta.cls}`}>{meta.label}</span>
                    {t.name}
                  </span>
                );
              })}
            </p>
          )}
          {installed && installed.platforms.length > 0 && (
            <p className="mt-1 text-[11px] text-ink-400">
              规则补丁：{installed.platforms.map(platformName).join("、")}
            </p>
          )}
        </div>
        {installed ? (
          <button
            onClick={() => act(s.id, () => uninstallSkill(s.id))}
            disabled={!!busy}
            className="shrink-0 rounded-md px-3 py-1.5 text-xs font-medium text-red-600 transition duration-150 hover:bg-red-50 disabled:opacity-50"
          >
            {busy === s.id ? "…" : "卸载"}
          </button>
        ) : (
          <button
            onClick={() => act(s.id, () => installSkill(s.source))}
            disabled={!!busy}
            className="btn-primary shrink-0 !px-3 !py-1.5 !text-xs"
          >
            {busy === s.id ? "安装中…" : "安装"}
          </button>
        )}
      </div>
    );
  };

  return (
    <main className="pb-24">
      <Nav />

      <div className="mx-auto max-w-6xl px-6">
        {/* ---------- 页头 ---------- */}
        <header className="mt-10 animate-fade-up">
          <p className="eyebrow">Agent Center · Agent 中枢</p>
          <h1 className="mt-3 text-3xl font-semibold tracking-tight text-ink-900">Agent 中枢</h1>
          <p className="mt-3 max-w-2xl text-sm leading-6 text-ink-500">
            千岸的自进化大脑：沉淀经验记忆、从人类反馈学习、按需安装技能扩展工具、并由进化 Agent
            提出改进提案——所有提案经人工审批后才生效，可一键回滚。
          </p>
        </header>

        {loading && (
          <p className="py-24 text-center font-mono text-xs uppercase tracking-[0.08em] text-ink-400">
            <span className="mr-2 inline-block h-1.5 w-1.5 animate-pulse-dot rounded-full bg-brand-500" />
            Loading · 加载中…
          </p>
        )}
        {error && (
          <p className="mt-6 rounded-lg bg-red-50 px-4 py-3 font-mono text-xs tracking-[0.04em] text-red-600">
            [ERROR] {error}
          </p>
        )}
        {notice && (
          <p className="mt-4 rounded-lg bg-amber-50 px-4 py-3 text-sm text-amber-600">{notice}</p>
        )}

        {!loading && overview && (
          <>
            {/* ---------- 概览指标 ---------- */}
            <section className="mt-8 grid animate-fade-up grid-cols-2 gap-3 sm:grid-cols-4">
              {[
                { label: "Tasks · 累计任务", value: overview.metrics.tasks },
                { label: "Experience · 沉淀经验", value: overview.memory.experiences.length },
                { label: "Feedback · 人类反馈", value: overview.memory.feedback.length },
                { label: "Skills · 已装技能", value: overview.skills.length },
              ].map((c) => (
                <div key={c.label} className="card px-5 py-4 transition duration-150 hover:shadow-sm">
                  <p className="font-mono text-3xl font-medium tabular-nums text-brand-800">{c.value}</p>
                  <p className="spec-label mt-2">{c.label}</p>
                </div>
              ))}
            </section>

            {/* ---------- 自愈趋势 ---------- */}
            <section className="card mt-8 animate-fade-up p-6 transition duration-150 hover:shadow-sm">
              <p className="eyebrow">Self-Healing · 自愈趋势</p>
              <p className="mt-2 text-xs leading-5 text-ink-400">
                每个任务触发合规自愈修订的比例。随经验沉淀，理想情况下应逐步下降——Agent 在生成阶段就避开了已知的坑。
              </p>
              {trend.length === 0 ? (
                <p className="mt-4 border-t border-ink-100 pt-4 text-xs text-ink-400">暂无任务。</p>
              ) : (
                <div className="mt-4 flex h-28 items-end gap-2 border-t border-ink-100 pt-4">
                  {trend.slice(-14).map((t) => (
                    <div key={t.task_id} className="flex flex-1 flex-col items-center gap-1" title={`${t.product_name}：修订率 ${(t.heal_rate * 100).toFixed(0)}%`}>
                      <div
                        className={`w-full rounded-t ${t.heal_rate === 0 ? "bg-green-200" : "bg-amber-400"}`}
                        style={{ height: `${Math.max(6, (t.heal_rate / maxRate) * 100)}%` }}
                      />
                      <span className="truncate text-[10px] text-ink-400">{t.product_name}</span>
                    </div>
                  ))}
                </div>
              )}
            </section>

            {/* ---------- 进化提案 ---------- */}
            <section className="card mt-8 animate-fade-up p-6 transition duration-150 hover:shadow-sm">
              <div className="flex items-start justify-between gap-4">
                <div>
                  <p className="eyebrow">Evolution · 进化提案</p>
                  <p className="mt-2 text-xs leading-5 text-ink-400">进化 Agent 分析记忆与反馈后提出的改进，人工审批后生效。</p>
                </div>
                <button
                  onClick={() => act("evolve", async () => {
                    const r = await evolveNow();
                    setNotice(r.result.generated ? "已产出新提案，请审批。" : `本轮未产出提案：${r.result.reason || ""}`);
                  })}
                  disabled={!!busy}
                  className="btn-primary shrink-0 !px-4 !py-1.5 !text-xs"
                >
                  {busy === "evolve" ? "分析中…" : "立即进化一轮"}
                </button>
              </div>

              <div className="mt-4 border-t border-ink-100 pt-4">
                {pending.length === 0 && (
                  <p className="text-xs text-ink-400">暂无待审批提案。</p>
                )}
                <div className="space-y-3">
                  {pending.map((p) => (
                    <div key={p.id} className="rounded-lg border border-amber-200 bg-amber-50/40 p-4">
                      <div className="flex items-center gap-2">
                        <span className={`rounded-md px-2 py-0.5 text-xs font-medium ${STATUS_META[p.status].cls}`}>{STATUS_META[p.status].label}</span>
                        <span className="text-xs font-medium text-ink-700">{p.type === "prompt_patch" ? "提示词改进" : "规则改进"} · {p.target}</span>
                        <span className="ml-auto font-mono text-[11px] tabular-nums text-ink-400">{fmtTime(p.ts)}</span>
                      </div>
                      <p className="mt-2 text-sm text-ink-800">{changeBrief(p)}</p>
                      <p className="mt-1 text-xs text-ink-500">依据：{p.reason}</p>
                      {p.evidence.length > 0 && (
                        <ul className="mt-2 space-y-1">
                          {p.evidence.map((e, i) => (
                            <li key={i} className="text-[11px] text-ink-400">· {e}</li>
                          ))}
                        </ul>
                      )}
                      <div className="mt-3 flex gap-2">
                        <button
                          onClick={() => act(p.id, () => decideProposal(p.id, "approve"))}
                          disabled={!!busy}
                          className="rounded-md bg-green-600 px-3 py-1.5 text-xs font-medium text-white transition duration-150 hover:bg-green-700 disabled:opacity-50"
                        >
                          批准并生效
                        </button>
                        <button
                          onClick={() => act(p.id, () => decideProposal(p.id, "reject"))}
                          disabled={!!busy}
                          className="btn-ghost !px-3 !py-1.5 !text-xs"
                        >
                          驳回
                        </button>
                      </div>
                    </div>
                  ))}
                </div>

                {history.length > 0 && (
                  <div className="mt-5 border-t border-ink-100 pt-4">
                    <h3 className="spec-label">历史决策</h3>
                    <div className="mt-2.5 space-y-2">
                      {history.map((p) => (
                        <div key={p.id} className="flex items-center gap-2 rounded-lg ring-1 ring-ink-100 px-3 py-2 transition duration-150 hover:bg-ink-50">
                          <span className={`shrink-0 rounded-md px-2 py-0.5 text-xs font-medium ${STATUS_META[p.status].cls}`}>{STATUS_META[p.status].label}</span>
                          <span className="truncate text-xs text-ink-600">{changeBrief(p)}</span>
                          {p.status === "applied" && (
                            <button
                              onClick={() => act(p.id, () => decideProposal(p.id, "rollback"))}
                              disabled={!!busy}
                              className="ml-auto shrink-0 rounded-md border border-brand-200 px-2.5 py-1 text-xs text-brand-700 transition duration-150 hover:bg-brand-50 disabled:opacity-50"
                            >
                              回滚
                            </button>
                          )}
                        </div>
                      ))}
                    </div>
                  </div>
                )}
              </div>
            </section>

            {/* ---------- 数据连接器 ---------- */}
            <section className="card mt-8 animate-fade-up p-6 transition duration-150 hover:shadow-sm">
              <p className="eyebrow">Connectors · 数据连接器</p>
              <p className="mt-2 text-xs leading-5 text-ink-400">
                连接器 = Agent 的外部感官：装上即点亮，核心引擎自动消费实时数据——实时汇率进单位经济测算、平台热搜进选品建议、竞品价格带进定价判断。
                卸下即回退内置演示数据，主流程永不断档。
              </p>
              <div className="mt-4 space-y-3 border-t border-ink-100 pt-4">
                {connectors.map((s) => renderStoreItem(s, true))}
                {connectors.length === 0 && <p className="text-xs text-ink-400">连接器目录为空。</p>}
              </div>
            </section>

            {/* ---------- 技能商店 ---------- */}
            <section className="card mt-8 animate-fade-up p-6 transition duration-150 hover:shadow-sm">
              <p className="eyebrow">Skill Store · 技能商店</p>
              <p className="mt-2 text-xs leading-5 text-ink-400">技能 = 规则补丁 + 新工具。安装后立即增强合规体检与 Agent 工具链，卸载即还原。</p>
              <div className="mt-4 space-y-3 border-t border-ink-100 pt-4">
                {skills.map((s) => renderStoreItem(s, false))}
                {skills.length === 0 && <p className="text-xs text-ink-400">技能目录为空。</p>}
              </div>
            </section>

            {/* ---------- 经验记忆 ---------- */}
            <section className="card mt-8 animate-fade-up p-6 transition duration-150 hover:shadow-sm">
              <p className="eyebrow">Memory · 经验记忆</p>
              <p className="mt-2 text-xs leading-5 text-ink-400">
                评审 Agent 每次任务后反思蒸馏的教训，会在下次生成同类文案时自动注入提示词。
                {overview.memory.enabled ? "" : "（记忆注入当前已关闭）"}
              </p>
              {overview.memory.experiences.length === 0 ? (
                <p className="mt-4 border-t border-ink-100 pt-4 text-xs text-ink-400">还没有沉淀经验，跑一单试试。</p>
              ) : (
                <div className="mt-4 space-y-2 border-t border-ink-100 pt-4">
                  {overview.memory.experiences.map((m) => (
                    <div key={m.id} className="flex items-start gap-3 rounded-lg px-3 py-2 ring-1 ring-ink-100 transition duration-150 hover:bg-ink-50">
                      <span className="mt-0.5 shrink-0 rounded-md bg-ink-100 px-2 py-0.5 text-[11px] text-ink-600">{platformName(m.platform)}</span>
                      <p className="min-w-0 flex-1 text-xs leading-5 text-ink-600">{m.lesson}</p>
                      <span className="shrink-0 font-mono text-[10px] tabular-nums text-ink-400">命中 {m.hit_count} 次</span>
                    </div>
                  ))}
                </div>
              )}

              <h3 className="spec-label mt-6">人类反馈</h3>
              {overview.memory.feedback.length === 0 ? (
                <p className="mt-2 text-xs text-ink-400">暂无反馈。在结果页给上架包点个赞或踩，Agent 会从中学习。</p>
              ) : (
                <div className="mt-2.5 space-y-2">
                  {overview.memory.feedback.slice(0, 12).map((f, i) => (
                    <div key={i} className="flex items-center gap-3 rounded-lg px-3 py-2 ring-1 ring-ink-100 transition duration-150 hover:bg-ink-50">
                      <span className={`shrink-0 text-sm ${f.rating > 0 ? "text-green-600" : "text-red-500"}`}>{f.rating > 0 ? "👍" : "👎"}</span>
                      <span className="shrink-0 rounded-md bg-ink-100 px-2 py-0.5 text-[11px] text-ink-600">{platformName(f.platform)}</span>
                      <span className="min-w-0 flex-1 truncate text-xs text-ink-500">{f.comment || "（无留言）"}</span>
                      <span className="shrink-0 font-mono text-[11px] tabular-nums text-ink-400">{fmtTime(f.ts)}</span>
                    </div>
                  ))}
                </div>
              )}
            </section>
          </>
        )}
      </div>
    </main>
  );
}
