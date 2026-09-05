"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import Link from "next/link";
import {
  AuditResult,
  EconomicsResult,
  PlatformListing,
  PLATFORM_META,
  auditDraft,
  createTask,
  fetchTask,
  runEconomics,
} from "@/lib/api";

interface SellerFields {
  title: string;
  brand: string;
  sku: string;
  bullet1: string;
  bullet2: string;
  bullet3: string;
  bullet4: string;
  bullet5: string;
  description: string;
  price: string;
  quantity: string;
  mainImage: string;
}

const EMPTY_FIELDS: SellerFields = {
  title: "",
  brand: "",
  sku: "",
  bullet1: "",
  bullet2: "",
  bullet3: "",
  bullet4: "",
  bullet5: "",
  description: "",
  price: "",
  quantity: "",
  mainImage: "",
};

const SAMPLE_IMAGE = "data:image/png;base64,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AIBwBwAA4Q4AAAh3AABAuAMAgHAHAACEOwAACHcAAEC4AwAAwh0AAIQ7AAAg3AEAAOEOAADCHQAAEO4AAIBwBwAA4Q4AAAh3AAAQ7gAAgHAHAACEOwAACHcAAEC4AwAAwh0AAIQ7AAAg3AEAQLgDAADCHQAAEO4AACDcAQAA4Q4AAAh3AAAQ7gAAgHAHAACEOwAACHcAAEC4AwCAcAcAAIQ7AAAg3AEAQLgDAADCHQAAEO4AACDcAQAA4Q4AAMIdAAAQ7gAAgHAHAADhDgAACHcAAEC4AwCAcAcAAIQ7AAAg3AEAQLgDAADCHQAAhDsAACDcAQAA4Q4AAMIdAAAQ7gAAgHAHAADhDgAACHcAABDuAACAcAcAAIQ7AAAIdwAAQLgDAADCHQAAhDsAACDcAQAA4Q4AAMIdAAAQ7gAAINwBAADhDgAACHcAABDuAACAcAcAAIQ7AAAIdwAAQLgDAIBwBwAAhDsAACDcAQBAuAMAAMIdAAAQ7gAAINwBAADhDgAACHcAABDuAACAcAcAAOEOAAAIdwAAQLgDAIBwBwAAhDsAACDcAQBAuAMAAMIdAACEuyUAAADhDgAACHcAABDuAACAcAcAAIQ7AAAIdwAAQLgDAADCHQAAhDsAACDcAQBAuAMAAMIdAAAQ7gAAINwBAADhDgAACHcAABDuAACAcAcAAP4fOMm+c8mSn88AAAAASUVORK5CYII=";

const SAMPLE_FILL: Partial<SellerFields> = {
  title: "Acme Portable Blender 380ml USB-C Rechargeable Juicer Cup for Smoothies",
  brand: "Acme",
  bullet1: "USB-C FAST CHARGE: full charge in 2 hours, blends up to 15 cups per charge",
  bullet2: "10-SECOND BLENDS: 6 titanium blades crush ice and frozen fruit in seconds",
  bullet3: "DETACHABLE EASY CLEAN: cup body separates from the motor base for rinsing",
  bullet4: "TRAVEL READY: 380ml leak-proof cup fits standard car cup holders",
  bullet5: "FOOD-GRADE MATERIAL: BPA-free Tritan cup body, 12-month warranty included",
  description:
    "Key Features: Acme portable blender with USB-C fast charge and 10-second blending power.\nSpecifications: 380ml BPA-free Tritan cup, 6 titanium blades, 2-hour full charge.\nWarranty: 12 months, friendly customer service within 24 hours.",
  price: "23.99",
  quantity: "100",
  mainImage: SAMPLE_IMAGE,
};

const ECON_DEFAULTS = {
  cost_cny: 12,
  weight_kg: 0.3,
  length_cm: 20,
  width_cm: 15,
  height_cm: 8,
  target_margin: 0.15,
  first_mile: "sea",
  turnover_months: 2,
  fixed_cost_cny: 3000,
  market_price_min: 12,
  market_price_max: 25,
};

const VERDICT_STYLE: Record<string, string> = {
  green: "bg-green-50 text-green-700",
  yellow: "bg-amber-50 text-amber-600",
  red: "bg-red-50 text-red-600",
};
const VERDICT_LABEL: Record<string, string> = {
  green: "可上",
  yellow: "需溢价",
  red: "建议放弃",
};

type MsgKind = "text" | "audit" | "economics" | "diff" | "progress";

interface Msg {
  id: number;
  role: "user" | "bot";
  kind: MsgKind;
  text: string;
  audit?: AuditResult;
  economics?: EconomicsResult;
  listing?: PlatformListing;
  before?: SellerFields;
}

const sleep = (ms: number) => new Promise((r) => setTimeout(r, ms));

function platformName(key: string) {
  return PLATFORM_META.find((p) => p.key === key)?.name || key;
}

export default function CopilotPage() {
  const [messages, setMessages] = useState<Msg[]>([]);
  const [input, setInput] = useState("");
  const iframeRef = useRef<HTMLIFrameElement | null>(null);
  const pendingRef = useRef<((data: unknown) => void) | null>(null);
  const idRef = useRef(1);
  const busyRef = useRef(false);

  const push = useCallback((m: Omit<Msg, "id">) => {
    const id = idRef.current++;
    setMessages((prev) => [...prev, { ...m, id }]);
    return id;
  }, []);

  const patch = useCallback((id: number, text: string) => {
    setMessages((prev) => prev.map((m) => (m.id === id ? { ...m, text } : m)));
  }, []);

  useEffect(() => {
    push({
      role: "bot",
      kind: "text",
      text: "我是千岸 Copilot，嵌在卖家后台旁边的对话侧栏。左边是一个模拟的 Amazon 上架表单。可以对我说：\n· 体检当前表单（合规扫描）\n· 算一单利润（定价建议）\n· 生成上架内容（跑流水线并回填）\n· 填充示例（先看到数据长什么样）",
    });
  }, [push]);

  useEffect(() => {
    const onMessage = (e: MessageEvent) => {
      const msg = e.data || {};
      if (msg.type === "QA_FIELDS" || msg.type === "QA_FILLED") {
        pendingRef.current?.(msg.payload);
        pendingRef.current = null;
      }
    };
    window.addEventListener("message", onMessage);
    return () => window.removeEventListener("message", onMessage);
  }, []);

  const postToForm = useCallback((msg: Record<string, unknown>): Promise<unknown> => {
    return new Promise((resolve, reject) => {
      const win = iframeRef.current?.contentWindow;
      if (!win) {
        reject(new Error("左侧页面还没加载好"));
        return;
      }
      const timer = setTimeout(() => {
        pendingRef.current = null;
        reject(new Error("与左侧页面通信超时"));
      }, 3000);
      pendingRef.current = (data) => {
        clearTimeout(timer);
        resolve(data);
      };
      win.postMessage(msg, "*");
    });
  }, []);

  const readForm = useCallback(async () => {
    const data = (await postToForm({ type: "QA_READ" })) as SellerFields | undefined;
    return data ? { ...EMPTY_FIELDS, ...data } : EMPTY_FIELDS;
  }, [postToForm]);

  const fillForm = useCallback(
    async (payload: Record<string, string>) => {
      const data = (await postToForm({ type: "QA_FILL", payload })) as
        | { filled?: number }
        | undefined;
      return data?.filled ?? 0;
    },
    [postToForm]
  );

  const cmdAudit = useCallback(async () => {
    let fields: SellerFields;
    try {
      fields = await readForm();
    } catch (e) {
      push({ role: "bot", kind: "text", text: `读不到左侧表单：${String(e)}` });
      return;
    }
    const filled = [fields.title, fields.description, fields.bullet1].filter(Boolean).length;
    if (!filled) {
      push({ role: "bot", kind: "text", text: "表单还是空的 —— 先对我说「填充示例」，或者直接在左边页面里填写内容，再让我体检。" });
      return;
    }
    const id = push({ role: "bot", kind: "progress", text: "正在读取表单内容并扫描 Amazon 规则…" });
    try {
      const result = await auditDraft({
        platform: "amazon",
        title: fields.title,
        bullets: [fields.bullet1, fields.bullet2, fields.bullet3, fields.bullet4, fields.bullet5].filter(Boolean),
        description: fields.description,
        images: fields.mainImage ? [fields.mainImage] : [],
      });
      patch(
        id,
        result.passed
          ? "体检完成，没有阻断级错误（warn 可在「/rules」页查规则出处）："
          : `体检完成，发现 ${result.issues.filter((i) => i.severity === "error").length} 个必须修复的错误：`
      );
      push({ role: "bot", kind: "audit", text: "", audit: result });
    } catch (e) {
      patch(id, `体检失败：${String(e)}`);
    }
  }, [patch, push, readForm]);

  const cmdEconomics = useCallback(async () => {
    const id = push({ role: "bot", kind: "progress", text: "正在按成本结构测算 5 个平台的保本价和建议价…" });
    try {
      const result = await runEconomics(ECON_DEFAULTS);
      patch(
        id,
        `按采购 ¥12、海运头程、目标净利率 15% 测算（成本参数可在工作台利润卡细调）。绿=可上，黄=市场带内需溢价，红=建议放弃：`
      );
      push({ role: "bot", kind: "economics", text: "", economics: result });
    } catch (e) {
      patch(id, `测算失败：${String(e)}`);
    }
  }, [patch, push]);

  const cmdGenerate = useCallback(async () => {
    let fields = EMPTY_FIELDS;
    try {
      fields = await readForm();
    } catch {
      // 表单读不到也能继续：用默认商品跑流水线
    }
    const existing = [fields.title, fields.description, fields.bullet1].filter(Boolean).length;
    const name =
      fields.title.slice(0, 40) || fields.brand || "Portable Blender 380ml";
    const selling =
      fields.description ||
      [fields.bullet1, fields.bullet2, fields.bullet3, fields.bullet4, fields.bullet5]
        .filter(Boolean)
        .join("；") ||
      "USB-C 快充，10 秒出汁，杯身可拆洗";

    const id = push({
      role: "bot",
      kind: "progress",
      text: existing
        ? "从当前表单内容出发，创建 Amazon 上架任务（理解商品 → 生成文案 → 合规体检 → 自愈修订）…"
        : "表单是空的，用演示商品跑一遍 Amazon 流水线（理解商品 → 生成文案 → 合规体检 → 自愈修订）…",
    });
    try {
      const { task_id } = await createTask({
        product_name: name,
        selling_points: selling,
        category: "home_kitchen",
        platforms: ["amazon"],
      });
      let lastStage = "";
      for (let i = 0; i < 120; i++) {
        await sleep(2000);
        const t = await fetchTask(task_id);
        if (t.status === "failed") throw new Error(t.error || "流水线失败");
        if (t.stage && t.stage !== lastStage) {
          lastStage = t.stage;
          patch(id, `流水线运行中：${t.stage}（任务 ${task_id.slice(0, 8)}）`);
        }
        if (t.status === "done") {
          const listing = t.listings[0];
          if (!listing) throw new Error("流水线完成但没有产出 listing");
          patch(id, `生成完成 ✓ Amazon listing 已产出${listing.revised_count ? `（自愈修订 ${listing.revised_count} 次）` : ""}。下面是「当前表单 → 生成内容」的差异预览：`);
          push({ role: "bot", kind: "diff", text: "", listing, before: fields });
          return;
        }
      }
      throw new Error("生成超时（4 分钟），可稍后到工作台查看该任务");
    } catch (e) {
      patch(id, `生成失败：${String(e)}`);
    }
  }, [patch, push, readForm]);

  const cmdSample = useCallback(async () => {
    try {
      const n = await fillForm(SAMPLE_FILL as Record<string, string>);
      push({ role: "bot", kind: "text", text: `已把示例商品填进左侧表单（${n} 个字段）。现在可以对我说「体检当前表单」看合规扫描，或「生成上架内容」跑一遍流水线。` });
    } catch (e) {
      push({ role: "bot", kind: "text", text: `填充失败：${String(e)}` });
    }
  }, [fillForm, push]);

  const fillFromListing = useCallback(
    async (listing: PlatformListing, before?: SellerFields) => {
      const payload: Record<string, string> = {
        title: listing.title,
        bullet1: listing.bullets[0] || "",
        bullet2: listing.bullets[1] || "",
        bullet3: listing.bullets[2] || "",
        bullet4: listing.bullets[3] || "",
        bullet5: listing.bullets[4] || "",
        description: listing.description,
      };
      const brand = listing.attributes?.brand || before?.brand;
      if (brand) payload.brand = brand;
      const img = listing.images[0];
      if (img && !img.startsWith("mock://")) payload.mainImage = img;
      try {
        const n = await fillForm(payload);
        push({
          role: "bot",
          kind: "text",
          text: `已把生成内容填进左侧表单（${n} 个字段）。价格建议参考「算一单利润」的结果；价格属于写操作，落到真实后台前都会先让你确认。`,
        });
      } catch (e) {
        push({ role: "bot", kind: "text", text: `填充失败：${String(e)}` });
      }
    },
    [fillForm, push]
  );

  const send = useCallback(
    async (raw: string) => {
      const text = raw.trim();
      if (!text || busyRef.current) return;
      if (/体检|合规|检查/.test(text)) {
        busyRef.current = true;
        try {
          await cmdAudit();
        } finally {
          busyRef.current = false;
        }
      } else if (/利润|定价|价格|赚钱/.test(text)) {
        busyRef.current = true;
        try {
          await cmdEconomics();
        } finally {
          busyRef.current = false;
        }
      } else if (/铺|上架|生成/.test(text)) {
        busyRef.current = true;
        try {
          await cmdGenerate();
        } finally {
          busyRef.current = false;
        }
      } else if (/示例|样例|demo/i.test(text)) {
        busyRef.current = true;
        try {
          await cmdSample();
        } finally {
          busyRef.current = false;
        }
      } else {
        push({
          role: "bot",
          kind: "text",
          text: "我目前支持这几件事：\n· 「体检当前表单」— 合规扫描\n· 「算一单利润」— 定价建议\n· 「生成上架内容」— 跑流水线并回填\n· 「填充示例」— 灌入演示数据",
        });
      }
    },
    [cmdAudit, cmdEconomics, cmdGenerate, cmdSample, push]
  );

  const submit = () => {
    const text = input;
    setInput("");
    push({ role: "user", kind: "text", text });
    send(text);
  };

  const CHIPS = ["体检当前表单", "算一单利润", "生成上架内容", "填充示例"];

  return (
    <div className="flex h-screen flex-col bg-ink-50">
      <header className="flex h-14 shrink-0 items-center justify-between border-b border-ink-100 bg-white/85 px-5 backdrop-blur">
        <div className="flex items-center gap-3">
          <p className="eyebrow">Copilot · 上架副驾</p>
          <span className="h-4 w-px bg-ink-200" />
          <h1 className="text-[15px] font-semibold tracking-tight text-ink-900">千岸 Copilot</h1>
          <span className="rounded-md bg-amber-50 px-2 py-0.5 text-xs font-medium text-amber-600">
            浏览器侧边栏演示
          </span>
        </div>
        <Link href="/workbench" className="text-xs text-ink-500 transition duration-150 hover:text-ink-900">
          ← 返回工作台
        </Link>
      </header>

      <div className="flex min-h-0 flex-1">
        {/* 左：模拟卖家后台 */}
        <div className="min-w-0 flex-1 border-r border-ink-200 bg-white">
          <iframe
            ref={iframeRef}
            src="/mock-seller-central.html"
            title="Mock Seller Central"
            className="h-full w-full"
          />
        </div>

        {/* 右：对话侧栏 */}
        <aside className="flex w-[400px] shrink-0 flex-col bg-white">
          <div className="min-h-0 flex-1 space-y-3 overflow-y-auto px-4 py-4">
            {messages.map((m) => (
              <div key={m.id} className={m.role === "user" ? "flex justify-end" : ""}>
                {m.role === "user" ? (
                  <p className="max-w-[85%] rounded-2xl rounded-br-sm bg-brand-700 px-3.5 py-2 text-sm text-white">
                    {m.text}
                  </p>
                ) : (
                  <div className="max-w-[95%] space-y-2">
                    {m.text && (
                      <p className="whitespace-pre-wrap text-[13px] leading-relaxed text-ink-700">{m.text}</p>
                    )}

                    {m.kind === "audit" && m.audit && (
                      <div
                        className={`rounded-lg border p-3 ${
                          m.audit.passed ? "border-green-200 bg-green-50/50" : "border-red-200 bg-red-50/50"
                        }`}
                      >
                        <p className={`text-xs font-bold ${m.audit.passed ? "text-green-700" : "text-red-600"}`}>
                          {m.audit.passed ? "✓ 体检通过" : "✗ 阻断级错误"} · {m.audit.issues.length} 条结果
                        </p>
                        <ul className="mt-2 space-y-1.5">
                          {m.audit.issues.map((i, idx) => (
                            <li key={idx} className="flex items-start gap-1.5 text-[12px] text-ink-600">
                              <span
                                className={`mt-1 h-1.5 w-1.5 shrink-0 rounded-full ${
                                  i.severity === "error" ? "bg-red-500" : "bg-amber-400"
                                }`}
                              />
                              <span>
                                <b className="font-mono text-ink-800">[{i.field}]</b> {i.message}
                              </span>
                            </li>
                          ))}
                        </ul>
                      </div>
                    )}

                    {m.kind === "economics" && m.economics && (
                      <div className="rounded-lg p-3 ring-1 ring-ink-100">
                        <p className="spec-label mb-2">
                          计费重 {m.economics.chargeable_weight_kg}kg · 汇率 {m.economics.fx_usd_cny}
                        </p>
                        <div className="space-y-2 border-t border-ink-100 pt-2">
                          {m.economics.platforms.map((p) => (
                            <div key={p.platform} className="flex items-center gap-2 text-xs">
                              <span className="w-20 shrink-0 font-medium text-ink-700">
                                {platformName(p.platform)}
                              </span>
                              <span className="font-mono tabular-nums text-ink-700">
                                ${p.suggested_price.toFixed(2)}
                              </span>
                              <span
                                className={`font-mono tabular-nums ${p.margin >= 0 ? "text-green-700" : "text-red-600"}`}
                              >
                                净利率 {(p.margin * 100).toFixed(1)}%
                              </span>
                              <span
                                className={`ml-auto rounded-md px-2 py-0.5 text-xs ${
                                  VERDICT_STYLE[p.verdict] || "bg-ink-100 text-ink-500"
                                }`}
                              >
                                {VERDICT_LABEL[p.verdict] || p.verdict}
                              </span>
                            </div>
                          ))}
                        </div>
                      </div>
                    )}

                    {m.kind === "diff" && m.listing && (
                      <div className="rounded-lg border border-amber-200 bg-amber-50/40 p-3">
                        <div className="space-y-2.5 text-[12px]">
                          <DiffRow label="标题" before={m.before?.title} after={m.listing.title} />
                          <DiffRow
                            label="五点"
                            before={(m.before?.bullet1 || "") && [m.before?.bullet1, m.before?.bullet2, m.before?.bullet3, m.before?.bullet4, m.before?.bullet5].filter(Boolean).join(" / ")}
                            after={m.listing.bullets.join(" / ")}
                          />
                          <DiffRow label="描述" before={m.before?.description} after={m.listing.description} />
                        </div>
                        <button
                          onClick={() => fillFromListing(m.listing!, m.before)}
                          className="btn-primary mt-3 !w-full !py-2 !text-xs"
                        >
                          一键填充到左侧表单
                        </button>
                      </div>
                    )}
                  </div>
                )}
              </div>
            ))}
          </div>

          <div className="shrink-0 border-t border-ink-100 px-4 py-3">
            <div className="mb-2 flex flex-wrap gap-1.5">
              {CHIPS.map((c) => (
                <button
                  key={c}
                  onClick={() => {
                    push({ role: "user", kind: "text", text: c });
                    send(c);
                  }}
                  className="rounded-md border border-ink-200 bg-white px-2.5 py-1 text-[11px] text-ink-500 shadow-xs transition duration-150 hover:border-brand-400 hover:text-brand-700"
                >
                  {c}
                </button>
              ))}
            </div>
            <div className="flex gap-2">
              <input
                value={input}
                onChange={(e) => setInput(e.target.value)}
                onKeyDown={(e) => e.key === "Enter" && submit()}
                placeholder="对我说：体检 / 算利润 / 生成 / 示例"
                className="field min-w-0 flex-1"
              />
              <button
                onClick={submit}
                disabled={!input.trim()}
                className="btn-primary !px-4 !py-2"
              >
                发送
              </button>
            </div>
          </div>
        </aside>
      </div>
    </div>
  );
}

function DiffRow({ label, before, after }: { label: string; before?: string; after: string }) {
  const changed = (before || "") !== (after || "");
  return (
    <div>
      <p className="mb-0.5 flex items-center gap-1.5 font-semibold text-ink-700">
        {label}
        {changed && <span className="rounded-md bg-amber-50 px-1.5 py-0.5 text-[10px] font-bold text-amber-600">有改动</span>}
      </p>
      {before && (
        <p className="truncate text-ink-400 line-through" title={before}>
          {before || "（空）"}
        </p>
      )}
      <p className={changed ? "text-ink-800" : "text-ink-400"} title={after}>
        {after || "（空）"}
      </p>
    </div>
  );
}
