/** Shared Spring tokens. Used by MotionUI; keep movement small for task-focused screens. */
export const springs = {
  snappy: { type: "spring", stiffness: 400, damping: 30 },
  gentle: { type: "spring", stiffness: 300, damping: 35 },
  smooth: { type: "spring", stiffness: 200, damping: 40, mass: 1.2 },
} as const;

export const shortExit = { duration: 0.14, ease: [0.22, 1, 0.36, 1] } as const;
