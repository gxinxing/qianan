"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useState } from "react";
import { useAuth } from "@/components/AuthProvider";

export default function RegisterPage() {
  const { signUp } = useAuth();
  const router = useRouter();

  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [confirm, setConfirm] = useState("");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const [done, setDone] = useState(false);

  async function onSubmit(e: React.FormEvent) {
    e.preventDefault();
    setError("");
    if (username.trim().length < 3) {
      setError("用户名至少 3 个字符");
      return;
    }
    if (password.length < 6) {
      setError("密码至少 6 位");
      return;
    }
    if (password !== confirm) {
      setError("两次输入的密码不一致");
      return;
    }
    setBusy(true);
    try {
      await signUp(username.trim(), password);
      setDone(true);
      setTimeout(() => router.replace("/workbench"), 900);
    } catch (err: any) {
      const msg = err?.message || err?.error_description || "注册失败，请更换用户名重试";
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
            <p className="text-[15px] font-semibold tracking-tight text-ink-900">注册千岸</p>
            <p className="font-mono text-[10px] uppercase tracking-[0.08em] text-ink-400">
              创建你的多租户工作空间
            </p>
          </div>
        </div>

        {done ? (
          <div className="rounded-md bg-emerald-50 px-3 py-4 text-center text-[13.5px] text-emerald-700">
            ✅ 注册成功，正在进入工作台…
          </div>
        ) : (
          <form onSubmit={onSubmit} className="space-y-4">
            <div>
              <label className="mb-1.5 block text-[13px] font-medium text-ink-700">用户名</label>
              <input
                value={username}
                onChange={(e) => setUsername(e.target.value)}
                autoComplete="username"
                required
                className="w-full rounded-lg border border-ink-200 bg-white px-3.5 py-2.5 text-[14px] text-ink-900 outline-none transition focus:border-brand-500 focus:ring-2 focus:ring-brand-100"
                placeholder="设置登录用户名（≥3 字符）"
              />
            </div>
            <div>
              <label className="mb-1.5 block text-[13px] font-medium text-ink-700">密码</label>
              <input
                type="password"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                autoComplete="new-password"
                required
                className="w-full rounded-lg border border-ink-200 bg-white px-3.5 py-2.5 text-[14px] text-ink-900 outline-none transition focus:border-brand-500 focus:ring-2 focus:ring-brand-100"
                placeholder="设置密码（≥6 位）"
              />
            </div>
            <div>
              <label className="mb-1.5 block text-[13px] font-medium text-ink-700">确认密码</label>
              <input
                type="password"
                value={confirm}
                onChange={(e) => setConfirm(e.target.value)}
                autoComplete="new-password"
                required
                className="w-full rounded-lg border border-ink-200 bg-white px-3.5 py-2.5 text-[14px] text-ink-900 outline-none transition focus:border-brand-500 focus:ring-2 focus:ring-brand-100"
                placeholder="再次输入密码"
              />
            </div>

            {error && (
              <p className="rounded-md bg-red-50 px-3 py-2 text-[12.5px] text-red-600">{error}</p>
            )}

            <button
              type="submit"
              disabled={busy}
              className="w-full rounded-lg bg-brand-800 py-2.5 text-[14px] font-medium text-white transition hover:bg-brand-700 disabled:opacity-60"
            >
              {busy ? "注册中…" : "注册并进入"}
            </button>
          </form>
        )}

        <p className="mt-5 text-center text-[13px] text-ink-400">
          已有账户？{" "}
          <Link href="/login" className="font-medium text-brand-700 hover:text-brand-800">
            去登录
          </Link>
        </p>
      </div>
    </div>
  );
}
