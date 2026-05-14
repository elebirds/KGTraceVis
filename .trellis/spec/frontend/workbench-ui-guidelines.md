# Workbench UI Guidelines

The maintained frontend under `web/` is a React + TypeScript + Vite workbench.
It uses Arco React for controls and ECharts for graph visualization. The old
dashboard under `web_legacy/` is only a migration reference.

## Structure Contract

- `web/src/api/` owns API clients and TypeScript contracts for FastAPI payloads.
- `web/src/app/` owns providers, routes, and the top-level shell.
- `web/src/components/` owns reusable UI and graph components.
- `web/src/features/` owns page-level modules such as Analysis and KG Studio.
- Do not put feature implementations back into a single large `App.tsx`.

## Visual Density Contract

The UI should read as a visual analytics workbench, not a generic dashboard.

- Sidebar width should stay around `200px`; use compact visible labels and keep
  descriptions in tooltips/title text rather than permanent second lines.
- Header height should stay around `50-56px`.
- Main content padding should stay around `16px 20px`.
- Page headers should be compact workbench headers, not hero sections that
  dominate the first viewport.
- Use cards for distinct repeated items, review panels, and data tables; avoid
  nesting cards inside cards for graph canvases.
- Keep metric cards low-height and sparse. Do not repeat large metric grids on
  every page unless the page is specifically a status overview.

## Graph Contract

KG and path views should make the graph the primary canvas.

- Use ECharts graph through the shared `KnowledgeGraph` component.
- Preserve node/edge selection callbacks so graph clicks update provenance and
  review targets.
- Keep KG Studio and RCA analysis roles separate:
  - KG Studio graph is for KG management, filtering, edge provenance, and
    review.
  - Analysis RCA Explorer is for explaining one selected case through ranked
    root-cause paths, supporting evidence, and selected-edge provenance.
- Keep graph filters in the graph canvas toolbar when possible. Avoid stacking
  a separate large filter block between the page header and graph.
- Default large KG graph labels to a low-noise mode. Provide an explicit labels
  toggle for dense graph exploration.
- KG Studio graph pages should allocate more vertical space to the graph than
  to tables or provenance text.
- Tables and provenance panels are auxiliary inspection tools; they should not
  visually overpower the graph.
- RCA Explorer should default to a focused selected path. Put ranking controls,
  the focused graph, and provenance/evidence in one workbench surface instead
  of stacking them as unrelated cards.

## Dependency Contract

The maintained `web/` stack is:

```text
React + TypeScript + Vite
@arco-design/web-react
echarts + echarts-for-react
React Router
plain CSS tokens
```

Do not reintroduce `antd`, `@ant-design/*`, Tailwind, `d3-force`, or
`lucide-react` into the maintained `web/` without an explicit migration plan.

## Wrong vs Correct

Wrong:

```text
App.tsx owns routes, API effects, upload forms, KG Studio, graph rendering,
and all review controls.
```

Correct:

```text
app/App.tsx wires routes and side effects.
features/analysis owns Analysis pages.
features/kg-studio owns KG Studio pages.
components/graph/KnowledgeGraph.tsx owns graph rendering.
```

Wrong:

```text
A KG graph is wrapped in a large card, surrounded by multiple metric cards,
and given less screen space than tables.
```

Correct:

```text
The graph is the main canvas; tables, filters, and provenance are compact
supporting controls.
```
