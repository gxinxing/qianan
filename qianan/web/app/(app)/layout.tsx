"use client";

import { RequireAuth } from "@/components/AuthGuard";

/** 受保护路由组：workbench / agent / copilot / files / admin / result 均需登录。 */
export default function AppLayout({ children }: { children: React.ReactNode }) {
  return <RequireAuth>{children}</RequireAuth>;
}
