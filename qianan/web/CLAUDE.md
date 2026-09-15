# Frontend motion system

- Shared Spring tokens: `lib/motion.ts` (`snappy`, `gentle`, `smooth`, short exits).
- Accessible primitives: `components/MotionUI.tsx`.
- Root `MotionProvider` respects the operating system's reduced-motion preference.
- `app/template.tsx` fades in the new route without retaining old App Router content or moving fixed navigation.
- Home: two restrained entry groups, button press feedback, platform disclosure, mobile sidebar and error feedback.
- Login/register: card entry, submit press, error/success feedback. Authentication behavior is unchanged.
- Avoid extra simultaneous entry groups: route + title + composer already use three.
- Reduced motion also explicitly disables height changes, custom-property sidebar movement and entry delays.
- Outgoing disclosures are inert, so hidden controls cannot receive keyboard focus.
