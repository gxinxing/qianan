# Frontend library modules

## Motion

`motion.ts` exports shared Spring transitions and a short exit curve. UI components consume these through `components/MotionUI.tsx`; avoid duplicating physical parameters per page. Keep `prefers-reduced-motion` behavior in the React primitives, including height and CSS custom-property animations.
