import Link from "next/link";
import { PLATFORM_META } from "@/lib/api";

const NAV = [
  { href: "/workbench", label: "工作台" },
  { href: "/rules", label: "规则库" },
  { href: "/agent", label: "Agent 中心" },
  { href: "/files", label: "文件管理" },
];

export default function Footer() {
  return (
    <footer className="mt-20 bg-brand-950 text-brand-100/70">
      <div className="mx-auto max-w-6xl px-6 py-14">
        <div className="grid gap-10 md:grid-cols-[1.4fr_1fr_1fr]">
          {/* 品牌 */}
          <div>
            <div className="flex items-center gap-2.5">
              <span className="flex h-7 w-7 items-center justify-center rounded-md bg-brand-700 text-[13px] font-semibold text-white">
                岸
              </span>
              <span className="text-[15px] font-semibold tracking-tight text-white">千岸</span>
              <span className="font-mono text-[11px] font-medium uppercase tracking-[0.08em] text-brand-300">
                QianAn
              </span>
            </div>
            <p className="mt-4 max-w-xs text-[13px] leading-6">
              一稿多岸 —— 多平台智能上新 Agent。一个设计稿，铺到千片海岸。
            </p>
            <p className="mt-5 font-mono text-[10px] uppercase tracking-[0.1em] text-brand-300/70">
              FastAPI · Next.js · Rules Engine
            </p>
          </div>

          {/* 平台 */}
          <div>
            <p className="font-mono text-[10px] font-medium uppercase tracking-[0.1em] text-brand-300">
              Platforms · 覆盖平台
            </p>
            <ul className="mt-4 space-y-2.5">
              {PLATFORM_META.map((p) => (
                <li key={p.key} className="flex items-center gap-2 text-[13px]">
                  <span
                    className="h-1.5 w-1.5 rounded-full"
                    style={{ background: p.key === "tiktokshop" ? "#e3e8f0" : p.dot }}
                  />
                  {p.name}
                </li>
              ))}
            </ul>
          </div>

          {/* 导航 */}
          <div>
            <p className="font-mono text-[10px] font-medium uppercase tracking-[0.1em] text-brand-300">
              Product · 产品
            </p>
            <ul className="mt-4 space-y-2.5">
              {NAV.map((n) => (
                <li key={n.href}>
                  <Link href={n.href} className="text-[13px] transition hover:text-white">
                    {n.label}
                  </Link>
                </li>
              ))}
            </ul>
          </div>
        </div>

        <div className="mt-12 flex flex-wrap items-center justify-between gap-3 border-t border-white/10 pt-6">
          <p className="text-[12px] text-brand-100/50">© 2026 千岸 QianAn Team</p>
          <p className="font-mono text-[10px] uppercase tracking-[0.1em] text-brand-100/40">
            AI+跨境黑客松巅峰赛 · 复赛 Demo
          </p>
        </div>
      </div>
    </footer>
  );
}
