"use client";

import { useRouter } from "next/navigation";
import { useEffect, type ReactNode } from "react";
import { useAuth } from "./AuthProvider";

/** 业务页守卫：未登录跳登录页（带 next 回跳）。首页/登录/注册页不要包它。 */
export function RequireAuth({ children }: { children: ReactNode }) {
  const { user, loading, ready } = useAuth();
  const router = useRouter();

  useEffect(() => {
    if (ready && !loading && !user) {
      const next = window.location.pathname + window.location.search;
      router.replace(`/login?next=${encodeURIComponent(next)}`);
    }
  }, [ready, loading, user, router]);

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

  if (!user) {
    return (
      <div className="flex min-h-[60vh] items-center justify-center text-ink-400">
        正在跳转到登录页…
      </div>
    );
  }

  return <>{children}</>;
}
