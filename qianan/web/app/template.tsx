"use client";

/** App Router entry fade. No retained old routes or transform around fixed navigation. */
import { motion, useReducedMotion } from "framer-motion";
import { springs } from "@/lib/motion";

export default function Template({ children }: { children: React.ReactNode }) {
  const reduce = useReducedMotion();
  return <motion.div initial={{ opacity: reduce ? 1 : 0 }} animate={{ opacity: 1 }} transition={reduce ? { duration: 0 } : springs.gentle}>{children}</motion.div>;
}
