"use client";

/** Accessible motion primitives: Spring entry/press/disclosure and a responsive sidebar.
 * Reduced motion removes displacement, scaling, height animation and stagger delays.
 */
import { useEffect, useState, type ReactNode } from "react";
import { AnimatePresence, motion, MotionConfig, useReducedMotion, useIsPresent, type HTMLMotionProps } from "framer-motion";
import { springs, shortExit } from "@/lib/motion";

export function MotionProvider({ children }: { children: ReactNode }) {
  return <MotionConfig reducedMotion="user" transition={springs.gentle}>{children}</MotionConfig>;
}

export function Enter({ children, delay = 0, ...props }: HTMLMotionProps<"div"> & { delay?: number }) {
  const reduce = useReducedMotion();
  return <motion.div {...props} initial={{ opacity: 0, y: reduce ? 0 : 10 }} animate={{ opacity: 1, y: 0 }} transition={reduce ? { duration: 0.1 } : { ...springs.gentle, delay }}>{children}</motion.div>;
}

export function PressButton({ children, disabled, ...props }: HTMLMotionProps<"button">) {
  const reduce = useReducedMotion();
  return <motion.button {...props} disabled={disabled} whileTap={reduce || disabled ? undefined : { scale: 0.97 }} transition={springs.snappy}>{children}</motion.button>;
}

function RevealPanel({ children, id }: { children: ReactNode; id?: string }) {
  const reduce = useReducedMotion();
  const present = useIsPresent();
  return (
    <motion.div
      id={id}
      inert={!present}
      initial={{ height: reduce ? "auto" : 0, opacity: 0 }}
      animate={{ height: "auto", opacity: 1 }}
      exit={{ height: reduce ? "auto" : 0, opacity: 0, transition: reduce ? { duration: 0 } : shortExit }}
      transition={reduce ? { duration: 0 } : springs.gentle}
      style={{ overflow: "hidden" }}
    >
      {children}
    </motion.div>
  );
}

export function Reveal({ open, children, id }: { open: boolean; children: ReactNode; id?: string }) {
  return <AnimatePresence initial={false}>{open && <RevealPanel key="panel" id={id}>{children}</RevealPanel>}</AnimatePresence>;
}

export function Feedback({ children, className, role = "status" }: { children: ReactNode; className?: string; role?: "alert" | "status" }) {
  const reduce = useReducedMotion();
  return <motion.div role={role} className={className} initial={{ opacity: 0, y: reduce ? 0 : 4 }} animate={{ opacity: 1, y: 0 }} transition={reduce ? { duration: 0 } : springs.snappy}>{children}</motion.div>;
}

export function SidebarMotion({ open, onClose, children }: { open: boolean; onClose: () => void; children: ReactNode }) {
  const reduce = useReducedMotion();
  const [mobile, setMobile] = useState(false);
  useEffect(() => {
    const query = window.matchMedia("(max-width: 700px)");
    const update = () => setMobile(query.matches);
    update();
    query.addEventListener("change", update);
    return () => query.removeEventListener("change", update);
  }, []);
  useEffect(() => {
    if (!open || !mobile) return;
    const onKey = (event: KeyboardEvent) => { if (event.key === "Escape") onClose(); };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [open, mobile, onClose]);
  return <motion.aside className={`agent-home-sidebar ${open ? "is-open" : ""}`} inert={mobile && !open} initial={false} animate={{ "--sidebar-offset": open ? "0%" : "-100%" }} transition={reduce ? { duration: 0 } : springs.gentle}>{children}</motion.aside>;
}
