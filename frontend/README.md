# GreenGuardian frontend

React + TypeScript + Vite + Tailwind v4, TanStack Query, React Router. Architecture: `docs/FRONTEND_ARCHITECTURE.md`.

```bash
npm install
npm run dev      # http://localhost:5173, proxies /api to http://localhost:8000 (override: VITE_DEV_API_TARGET)
npm test         # vitest
npm run build    # type-check + production build
```

Conventions: future (V2+) surfaces render through `CapabilityGate` and never show invented output. The route registry (`src/app/routes.ts`) is the single source for navigation, mode-awareness and status labels: "In development" means an MVP surface that is not built yet, "Coming soon" means V2+.
