"use client";

import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { useState } from "react";
import { useAuth } from "./AuthProvider";

const LINKS = [
  { href: "/", label: "首页" },
  { href: "/workbench", label: "工作台" },
  { href: "/batch", label: "批量上新" },
  { href: "/rules", label: "规则库" },
  { href: "/agent", label: "Agent" },
  { href: "/files", label: "文件管理" },
  { href: "/admin", label: "后台管理" },
];

function UserMenu() {
  const { user, ready, signOut } = useAuth();
  const router = useRouter();

  if (!ready) {
    return <span className="ml-3 hidden h-7 w-16 animate-pulse rounded-full bg-ink-100 lg:block" />;
  }

  if (!user) {
    return (
      <Link
        href="/login"
        className="ml-3 hidden rounded-full bg-brand-800 px-3.5 py-1.5 text-[12.5px] font-medium text-white transition hover:bg-brand-700 lg:block"
      >
        登录
      </Link>
    );
  }

  return (
    <div className="ml-3 hidden items-center gap-2 lg:flex">
      <span className="rounded-full bg-ink-50 px-2.5 py-1 font-mono text-[11px] text-ink-500">
        {user.username || user.uid}
      </span>
      <button
        onClick={async () => {
          await signOut();
          router.replace("/login");
        }}
        className="rounded-full border border-ink-200 px-2.5 py-1 text-[12px] text-ink-500 transition hover:bg-ink-50"
      >
        退出
      </button>
    </div>
  );
}

export default function Nav() {
  const pathname = usePathname();
  const [open, setOpen] = useState(false);
  const { user, ready, signOut } = useAuth();

  return (
    <header className="sticky top-0 z-40 border-b border-ink-100 bg-white/85 backdrop-blur">
      <nav className="mx-auto flex h-14 max-w-6xl items-center justify-between px-6">
        <Link href="/" className="group flex items-center gap-2.5" onClick={() => setOpen(false)}>
          <span className="flex h-7 w-7 items-center justify-center rounded-md bg-brand-800 text-[13px] font-semibold text-white shadow-sm transition group-hover:bg-brand-700">
            岸
          </span>
          <span className="text-[15px] font-semibold tracking-tight text-ink-900">千岸</span>
          <span className="font-mono text-[11px] font-medium uppercase tracking-[0.08em] text-ink-400">
            QianAn
          </span>
        </Link>

        {/* 桌面导航 */}
        <div className="hidden items-center gap-1 md:flex">
          {LINKS.map((l) => {
            const active = pathname === l.href;
            return (
              <Link
                key={l.href}
                href={l.href}
                className={`relative rounded-md px-3 py-1.5 text-[13px] transition duration-150 ${
                  active
                    ? "font-medium text-brand-800"
                    : "text-ink-500 hover:bg-ink-50 hover:text-ink-800"
                }`}
              >
                {l.label}
                {active && (
                  <span className="absolute inset-x-3 -bottom-[9px] h-0.5 rounded-full bg-brand-700" />
                )}
              </Link>
            );
          })}
          <UserMenu />
        </div>

        {/* 移动端：当前页标识 + 菜单按钮 */}
        <div className="flex items-center gap-2 md:hidden">
          <span className="font-mono text-[10px] uppercase tracking-[0.08em] text-ink-400">
            {LINKS.find((l) => l.href === pathname)?.label || ""}
          </span>
          <button
            onClick={() => setOpen((v) => !v)}
            aria-label="菜单"
            aria-expanded={open}
            className="flex h-9 w-9 flex-col items-center justify-center gap-[5px] rounded-md border border-ink-200 bg-white text-ink-700 shadow-xs transition hover:bg-ink-50"
          >
            <span
              className={`h-px w-4 bg-current transition-transform duration-200 ${open ? "translate-y-[3px] rotate-45" : ""}`}
            />
            <span
              className={`h-px w-4 bg-current transition-transform duration-200 ${open ? "-translate-y-[3px] -rotate-45" : ""}`}
            />
          </button>
        </div>
      </nav>

      {/* 移动端下拉面板 */}
      {open && (
        <div className="border-t border-ink-100 bg-white/95 backdrop-blur md:hidden">
          <div className="mx-auto grid max-w-6xl grid-cols-2 gap-1 px-6 py-3">
            {LINKS.map((l) => {
              const active = pathname === l.href;
              return (
                <Link
                  key={l.href}
                  href={l.href}
                  onClick={() => setOpen(false)}
                  className={`rounded-md px-3 py-2.5 text-[13px] transition ${
                    active
                      ? "bg-brand-50 font-medium text-brand-800"
                      : "text-ink-600 hover:bg-ink-50"
                  }`}
                >
                  {l.label}
                </Link>
              );
            })}
            <div className="col-span-2 mt-1 border-t border-ink-100 pt-2">
              {ready && user ? (
                <button
                  onClick={async () => {
                    await signOut();
                    setOpen(false);
                    window.location.href = "/login";
                  }}
                  className="w-full rounded-md bg-ink-50 px-3 py-2.5 text-[13px] text-ink-600"
                >
                  退出登录（{user.username || user.uid}）
                </button>
              ) : (
                <Link
                  href="/login"
                  onClick={() => setOpen(false)}
                  className="block rounded-md bg-brand-800 px-3 py-2.5 text-center text-[13px] font-medium text-white"
                >
                  登录 / 注册
                </Link>
              )}
            </div>
          </div>
        </div>
      )}
    </header>
  );
}
