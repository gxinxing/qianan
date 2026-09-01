"use client";

import { useEffect, useState } from "react";
import { fetchRules, PLATFORM_META, type PlatformRule } from "@/lib/api";
import Nav from "@/components/Nav";

const DEPTH_META: Record<string, { label: string; cls: string }> = {
  deep: { label: "做深", cls: "bg-green-50 text-green-700" },
  reuse: { label: "机制复用", cls: "bg-brand-50 text-brand-700" },
  simple: { label: "简化", cls: "bg-amber-50 text-amber-600" },
};

const CHECK_TYPE: Record<string, string> = {
  length: "长度",
  length_each: "逐条长度",
  count: "数量",
  banned_words: "禁用词",
  image_spec: "主图规范",
  required_attrs: "必填属性",
  required_sections: "必备段落",
  locale_coverage: "语言覆盖",
};

const BANNED_GROUP: Record<string, string> = {
  promotional: "促销用语",
  claims: "绝对化宣称",
  restricted: "受限宣称",
  trademark: "商标侵权",
};

const pct = (v?: number) => (typeof v === "number" ? `${Math.round(v * 100)}%` : "—");

function lastMileLabel(eco: NonNullable<PlatformRule["economics"]>): string {
  const ful = eco.fulfillment;
  if (ful?.type === "fba_tiers" && ful.tiers?.length) {
    const fees = ful.tiers.map((t) => t.fee);
    return `FBA 跳档 $${Math.min(...fees)}–${Math.max(...fees)}`;
  }
  if (typeof ful?.fee === "number") return `$${ful.fee}/单`;
  return "—";
}

export default function RulesPage() {
  const [rules, setRules] = useState<Record<string, PlatformRule>>({});
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    fetchRules()
      .then(setRules)
      .catch((e) => setError(`规则库加载失败：${String(e)}`))
      .finally(() => setLoading(false));
  }, []);

  const ordered = PLATFORM_META.map((p) => rules[p.key]).filter(Boolean) as PlatformRule[];
  const totalChecks = ordered.reduce((n, r) => n + (r.complianceChecks?.length || 0), 0);
  const totalBanned = ordered.reduce(
    (n, r) =>
      n +
      Object.values(r.bannedWords || {}).reduce(
        (m, v) => m + (Array.isArray(v) ? v.length : 0),
        0
      ),
    0
  );
  const totalLocales = new Set(ordered.flatMap((r) => r.locales || [])).size;

  return (
    <main className="pb-24">
      <Nav />

      <div className="mx-auto max-w-6xl px-6">
        {/* ---------- 页头 ---------- */}
        <header className="mt-10 animate-fade-up">
          <p className="eyebrow">Rules Engine · 规则引擎</p>
          <h1 className="mt-3 text-3xl font-semibold tracking-tight text-ink-900">规则库</h1>
          <p className="mt-3 max-w-2xl text-sm leading-6 text-ink-500">
            各平台上架规范以结构化 JSON（rules.v1）落库，规则引擎直接消费——合规是代码校验出来的，
            不是模型声称的。来源为各平台卖家中心公开文档。
          </p>
        </header>

        {loading && (
          <p className="py-24 text-center font-mono text-xs uppercase tracking-[0.08em] text-ink-400">
            <span className="mr-2 inline-block h-1.5 w-1.5 animate-pulse-dot rounded-full bg-brand-500" />
            Loading rules.v1 · 加载中…
          </p>
        )}
        {error && (
          <p className="py-24 text-center font-mono text-xs tracking-[0.04em] text-red-600">
            [ERROR] {error}
          </p>
        )}

        {!loading && !error && (
          <>
            {/* ---------- 统计带 ---------- */}
            <div className="mt-8 grid animate-fade-up grid-cols-2 gap-3 sm:grid-cols-4">
              {[
                { label: "Platforms · 平台", value: ordered.length },
                { label: "Checks · 确定性校验项", value: totalChecks },
                { label: "Banned Words · 禁用词", value: totalBanned },
                { label: "Locales · 输出语言", value: totalLocales },
              ].map((s) => (
                <div key={s.label} className="card px-5 py-4 transition duration-150 hover:shadow-sm">
                  <p className="font-mono text-3xl font-medium tabular-nums text-brand-800">
                    {s.value}
                  </p>
                  <p className="spec-label mt-2">{s.label}</p>
                </div>
              ))}
            </div>

            {/* ---------- 平台规格卡 ---------- */}
            <div className="mt-8 grid animate-fade-up gap-6 lg:grid-cols-2">
              {ordered.map((r) => {
                const depth = DEPTH_META[r.demoDepth] || {
                  label: r.demoDepth,
                  cls: "bg-ink-100 text-ink-500",
                };
                const dot = PLATFORM_META.find((p) => p.key === r.platform)?.dot || "#999";
                const bannedGroups = Object.entries(r.bannedWords || {}).filter(
                  ([, v]) => Array.isArray(v) && v.length > 0
                ) as [string, string[]][];
                const note = r.bannedWords?.restrictedNote;
                return (
                  <section
                    key={r.platform}
                    className="card relative space-y-6 overflow-hidden p-6 pt-7 transition duration-150 hover:shadow-md"
                  >
                    {/* 平台色带 */}
                    <span
                      className="absolute inset-x-0 top-0 h-0.5"
                      style={{ background: dot }}
                    />

                    {/* 头部 */}
                    <div>
                      <div className="flex flex-wrap items-center gap-2">
                        <span
                          className="h-2 w-2 rounded-full ring-2 ring-ink-100"
                          style={{ background: dot }}
                        />
                        <h2 className="text-base font-semibold text-ink-900">{r.displayName}</h2>
                        <span
                          className={`rounded-full px-2 py-0.5 text-xs font-medium ${depth.cls}`}
                        >
                          {depth.label}
                        </span>
                        {r.updated && (
                          <span className="ml-auto font-mono text-[11px] tabular-nums text-ink-400">
                            核对于 {r.updated}
                          </span>
                        )}
                      </div>
                      {r.source && (
                        <p className="mt-2 text-xs leading-5 text-ink-400">{r.source}</p>
                      )}
                    </div>

                    {/* 语言与站点 */}
                    <div>
                      <h3 className="spec-label">语言与站点</h3>
                      <div className="mt-2.5 flex flex-wrap gap-1.5">
                        {(r.locales || []).map((l) => (
                          <span
                            key={l}
                            className="rounded-md bg-ink-100 px-2 py-0.5 font-mono text-[11px] text-ink-600"
                          >
                            {l}
                          </span>
                        ))}
                        {(r.marketplaces || []).map((m) => (
                          <span
                            key={m}
                            className="rounded-md bg-brand-50 px-2 py-0.5 text-[11px] font-medium text-brand-700"
                          >
                            {m}
                          </span>
                        ))}
                      </div>
                    </div>

                    {/* 标题约束 */}
                    {r.title && (
                      <div>
                        <h3 className="spec-label">标题约束</h3>
                        <p className="mt-2.5 text-sm text-ink-700">
                          ≤{" "}
                          <span className="font-mono font-medium tabular-nums text-brand-800">
                            {r.title.maxLength}
                          </span>{" "}
                          字符
                          {r.title.recommendedLength && (
                            <span className="text-ink-400">
                              {" "}
                              · 推荐{" "}
                              <span className="font-mono tabular-nums">
                                {r.title.recommendedLength[0]}–{r.title.recommendedLength[1]}
                              </span>
                            </span>
                          )}
                        </p>
                        {r.title.formula && (
                          <p className="mt-1.5 text-xs leading-5 text-ink-400">{r.title.formula}</p>
                        )}
                      </div>
                    )}

                    {/* 主图规范 */}
                    {r.mainImage && (
                      <div>
                        <h3 className="spec-label">主图规范</h3>
                        <p className="mt-2.5 text-sm text-ink-700">
                          ≥{" "}
                          <span className="font-mono font-medium tabular-nums text-brand-800">
                            {r.mainImage.minWidth}×{r.mainImage.minHeight}
                          </span>
                          {r.mainImage.background === "white" && " · 纯白背景"}
                          {r.mainImage.background === "clean" && " · 干净背景"}
                        </p>
                        <p className="mt-1.5 text-xs text-ink-400">
                          {[
                            r.mainImage.noText && "无文字",
                            r.mainImage.noWatermark && "无水印",
                            r.mainImage.noBorder && "无边框",
                          ]
                            .filter(Boolean)
                            .join(" · ")}
                          {" · 体检时 PIL 实测尺寸与四角白底"}
                        </p>
                      </div>
                    )}

                    {/* 禁用词 */}
                    {bannedGroups.length > 0 && (
                      <div>
                        <h3 className="spec-label">禁用词</h3>
                        <div className="mt-2.5 space-y-2.5">
                          {bannedGroups.map(([group, words]) => (
                            <div key={group}>
                              <p className="text-xs font-medium text-ink-500">
                                {BANNED_GROUP[group] || group}
                              </p>
                              <div className="mt-1.5 flex flex-wrap gap-1.5">
                                {words.map((w) => (
                                  <span
                                    key={w}
                                    className="rounded-md bg-red-50 px-2 py-0.5 text-xs text-red-600"
                                  >
                                    {w}
                                  </span>
                                ))}
                              </div>
                            </div>
                          ))}
                        </div>
                        {typeof note === "string" && (
                          <p className="mt-2 text-xs leading-5 text-ink-400">{note}</p>
                        )}
                      </div>
                    )}

                    {/* 费率 */}
                    {r.economics && (
                      <div>
                        <h3 className="spec-label">费率 · 定价引擎消费</h3>
                        <div className="mt-2.5 grid grid-cols-2 gap-2 sm:grid-cols-3">
                          {[
                            { label: "佣金率", value: pct(r.economics.commissionRate) },
                            { label: "广告 TACOS", value: pct(r.economics.adTacosDefault) },
                            {
                              label: "退货率",
                              value:
                                pct(r.economics.returnRateDefault) +
                                (r.economics.returnHandlingFee != null
                                  ? ` · 处理费 $${r.economics.returnHandlingFee}`
                                  : ""),
                            },
                            { label: "尾程", value: lastMileLabel(r.economics) },
                            {
                              label: "仓储",
                              value:
                                (r.economics.fulfillment?.monthlyStoragePerCubicMeter ??
                                  r.economics.monthlyStoragePerCubicMeter) != null
                                  ? `$${r.economics.fulfillment?.monthlyStoragePerCubicMeter ?? r.economics.monthlyStoragePerCubicMeter}/m³·月`
                                  : "—",
                            },
                            { label: "VAT", value: pct(r.economics.vatRate) },
                          ].map((cell) => (
                            <div
                              key={cell.label}
                              className="rounded-lg bg-ink-50 px-3 py-2 transition duration-150 hover:bg-ink-100"
                            >
                              <p className="spec-label">{cell.label}</p>
                              <p className="mt-1 font-mono text-xs font-medium tabular-nums text-ink-800">
                                {cell.value}
                              </p>
                            </div>
                          ))}
                        </div>
                        {r.economics.dutyNote && (
                          <p className="mt-2 text-xs leading-5 text-ink-400">
                            {r.economics.dutyNote}
                          </p>
                        )}
                      </div>
                    )}

                    {/* 合规体检清单 */}
                    {(r.complianceChecks || []).length > 0 && (
                      <div>
                        <h3 className="spec-label">
                          合规体检 ·{" "}
                          <span className="tabular-nums">{r.complianceChecks!.length}</span>{" "}
                          项确定性校验
                        </h3>
                        <ul className="mt-2.5 divide-y divide-ink-100 border-y border-ink-100">
                          {r.complianceChecks!.map((c) => (
                            <li
                              key={c.id}
                              className="flex items-center gap-2.5 py-2 text-xs transition duration-150 hover:bg-ink-50"
                            >
                              <span
                                className={`h-1.5 w-1.5 shrink-0 rounded-full ${
                                  c.severity === "error" ? "bg-red-500" : "bg-amber-400"
                                }`}
                              />
                              <span className="font-medium text-ink-700">
                                {CHECK_TYPE[c.type] || c.type}
                              </span>
                              <span className="font-mono text-[11px] text-ink-400">{c.id}</span>
                              <span
                                className={`ml-auto rounded-full px-1.5 py-0.5 font-mono text-[10px] ${
                                  c.severity === "error"
                                    ? "bg-red-50 text-red-600"
                                    : "bg-amber-50 text-amber-600"
                                }`}
                              >
                                {c.severity === "error" ? "error" : "warn"}
                              </span>
                            </li>
                          ))}
                        </ul>
                      </div>
                    )}
                  </section>
                );
              })}
            </div>
          </>
        )}
      </div>
    </main>
  );
}
