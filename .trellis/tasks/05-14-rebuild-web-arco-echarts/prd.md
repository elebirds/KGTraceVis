# rebuild React Arco ECharts frontend

## Goal

Freeze the current KGTraceVis React dashboard as `web_legacy/`, then rebuild a clean `web/` frontend with React, TypeScript, Vite, Arco React, and ECharts. The new frontend should keep the existing FastAPI `/api/*` contracts, improve the research-workbench layout, and replace handmade D3/SVG KG rendering with reusable ECharts graph components.

## What I already know

* The current frontend is tracked under `web/` with 15 Git-tracked files.
* `web/src/App.tsx`, `web/src/KGStudioWorkspace.tsx`, and `web/src/styles.css` are large monolithic files.
* The current frontend uses Ant Design, Tailwind, and `d3-force`.
* The target stack is React + TypeScript + Vite + Arco React + ECharts.
* RootLens is a UX and graph-interaction reference only; it should not become the source of truth.
* The FastAPI backend and Python analysis pipeline remain authoritative and should not change for this task.

## Requirements

* Move the existing `web/` to `web_legacy/` as a migration reference.
* Create a new `web/` with a clean feature-based structure.
* Use Arco React as the UI framework and ECharts for graph rendering.
* Preserve current API contracts for bootstrap, run upload, run history, run detail, KG Studio, feedback, KG drafts, and source draft generation.
* Implement the workbench shell, Home, Analysis, KG Studio, and Experiments pages.
* Implement a reusable `KnowledgeGraph` component for KG Studio graph browsing and Analysis path visualization.
* Avoid reintroducing Ant Design, Tailwind, or D3 into the new frontend.
* Update documentation for the new frontend stack and startup flow.

## Acceptance Criteria

* [ ] `web_legacy/` contains the old tracked frontend files.
* [ ] `web/` builds as a fresh React + TypeScript + Vite app.
* [ ] `web/package.json` uses Arco React and ECharts dependencies, not AntD, Tailwind, or D3.
* [ ] API client and TypeScript contracts are available under `web/src/api/`.
* [ ] App routes cover Home, Analysis live/history/detail, KG Studio overview/sources/graph/review/drafts, and Experiments.
* [ ] KG Studio graph uses ECharts and supports selection linked to edge provenance.
* [ ] Analysis detail shows evidence, linking, consistency, candidate paths, and review actions.
* [ ] `cd web && npm run typecheck` passes.
* [ ] `cd web && npm run build` passes.

## Out of Scope

* Changing FastAPI routes or Python pipeline behavior.
* Introducing full Arco Pro.
* Directly merging RootLens Vue code.
* Building a complete enterprise admin system.

## Technical Notes

* Relevant current files: `web/src/App.tsx`, `web/src/KGStudioWorkspace.tsx`, `web/src/api.ts`, `web/src/types.ts`, `web/src/state.ts`.
* RootLens reference files inspected previously: `src/components/graphs/KnowledgeForceGraph.vue`, `src/views/GraphExploreView.vue`, and its Arco/ECharts workspace layout.
* Project specs emphasize contract preservation, traceability, and avoiding duplicated core logic.
