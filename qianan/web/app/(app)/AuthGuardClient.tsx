"use client";

import { RequireAuth } from "@/components/AuthGuard";

export default function AuthGuardClient({ children }: { children: React.ReactNode }) {
  return <RequireAuth>{children}</RequireAuth>;
}
