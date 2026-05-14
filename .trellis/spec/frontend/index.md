# Frontend Development Guidelines

KGTraceVis frontend work lives under `web/` and supports a local research
workbench for anomaly evidence inspection, KG exploration, and review capture.

## Pre-Development Checklist

Before writing frontend code:

1. Preserve the FastAPI `/api/*` contracts in `web/src/api/`.
2. Keep legacy reference code under `web_legacy/`; do not modify it for new UI
   behavior.
3. Use Arco React for application controls and ECharts for graph exploration.
4. Keep page modules feature-scoped instead of rebuilding a monolithic
   `App.tsx`.
5. Check visual density against the RootLens-style workbench conventions below.

## Guidelines Index

| Guide | Description | Status |
|-------|-------------|--------|
| [Workbench UI Guidelines](./workbench-ui-guidelines.md) | Frontend structure, density, graph, and visual analytics conventions | Active |

## Quality Check

Run at minimum:

```bash
cd web
npm run typecheck
npm run build
```

Also verify that new `web/` code does not reintroduce Ant Design, Tailwind, or
D3 dependencies unless a future task explicitly changes the frontend stack.

