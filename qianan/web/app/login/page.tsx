"use client";

import { Suspense, useState } from "react";
import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { useAuth } from "@/components/AuthProvider";

function LoginInner() {
  const { signIn } = useAuth();
  const router = useRouter();
  const params = useSearchParams();
  const next = params.get("next") || "/workbench";

  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  async function onSubmit(e: React.FormEvent) {
    e.preventDefault();
    setError("");
    setBusy(true);
    try {
      await signIn(username.trim(), password);
      router.replace(next);
    } catch (err: any) {
      const msg = err?.message || err?.error_description || "登录失败，请检查用户名和密码";
      setError(msg);
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="mx-auto flex min-h-[calc(100vh-3.5rem)] max-w-md flex-col justify-center px-6">
      <div className="rounded-2xl border border-ink-100 bg-white p-8 shadow-sm">
        <div className="mb-6 flex items-center gap-2.5">
          <span className="flex h-8 w-8 items-center justify-center rounded-md bg-brand-800 text-[15px] font-semibold text-white">
            岸
          </span>
          <div>
            <p className="text-[15px] font-semibold tracking-tight text-ink-900">登录千岸</p>
            <p className="font-mono text-[10px] uppercase tracking-[0.08em] text-ink-400">
              一稿多岸 · 跨境上新 Agent
            </p>
          </div>
        </div>

        <form onSubmit={onSubmit} className="space-y-4">
          <div>
            <label className="mb-1.5 block text-[13px] font-medium text-ink-700">用户名</label>
            <input
              value={username}
              onChange={(e) => setUsername(e.target.value)}
              autoComplete="username"
              required
              className="w-full rounded-lg border border-ink-200 bg-white px-3.5 py-2.5 text-[14px] text-ink-900 outline-none transition focus:border-brand-500 focus:ring-2 focus:ring-brand-100"
              placeholder="你的登录用户名"
            />
          </div>
          <div>
            <label className="mb-1.5 block text-[13px] font-medium text-ink-700">密码</label>
            <input
              type="password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              autoComplete="current-password"
              required
              className="w-full rounded-lg border border-ink-200 bg-white px-3.5 py-2.5 text-[14px] text-ink-900 outline-none transition focus:border-brand-500 focus:ring-2 focus:ring-brand-100"
              placeholder="••••••••"
            />
          </div>

          {error && (
            <p role="alert" className="rounded-md bg-red-50 px-3 py-2 text-[12.5px] text-red-600">
              {error}
            </p>
          )}

          <button
            type="submit"
            disabled={busy}
            className="w-full rounded-lg bg-brand-800 py-2.5 text-[14px] font-medium text-white transition hover:bg-brand-700 disabled:opacity-60"
          >
            {busy ? "登录中…" : "登录"}
          </button>
        </form>

        <p className="mt-5 text-center text-[13px] text-ink-400">
          还没有账户？{" "}
          <Link href="/register" className="font-medium text-brand-700 hover:text-brand-800">
            立即注册
          </Link>
        </p>
      </div>
    </div>
  );
}

export default function LoginPage() {
  return (
    <Suspense fallback={<div className="p-10 text-center text-ink-400">加载中…</div>}>
      <LoginInner />
    </Suspense>
  );
}
