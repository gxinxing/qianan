"use client";

import { useRouter } from "next/navigation";
import { useEffect, type ReactNode } from "react";
import { useAuth } from "./AuthProvider";

/** 业务页守卫：未登录跳登录页（带 next 回跳）。首页/登录/注册页不要包它。 */
export function RequireAuth({ children }: { children: ReactNode }) {
  const { user, loading, ready, requireAuth } = useAuth();
  const router = useRouter();

  // 后端未开启强制鉴权（演示模式）时放行游客，与 /api/health 的 auth.require_auth 对齐；
  // 否则会出现「后端允许匿名、前端却把用户拦在登录墙外」的自相矛盾。
  const anonymousAllowed = requireAuth === false;

  useEffect(() => {
    if (ready && !loading && !user && !anonymousAllowed) {
      const next = window.location.pathname + window.location.search;
      router.replace(`/login?next=${encodeURIComponent(next)}`);
    }
  }, [ready, loading, user, anonymousAllowed, router]);

  if (!ready || loading) {
    return (
      <div className="flex min-h-[60vh] items-center justify-center">
        <div className="flex items-center gap-3 text-ink-400">
          <span className="h-2 w-2 animate-pulse-dot rounded-full bg-brand-500" />
          正在校验登录态…
        </div>
      </div>
    );
  }

  if (!user && !anonymousAllowed) {
    return (
      <div className="flex min-h-[60vh] items-center justify-center text-ink-400">
        正在跳转到登录页…
      </div>
    );
  }

  return <>{children}</>;
}
