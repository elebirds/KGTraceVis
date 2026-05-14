# brainstorm: KG Studio source-to-KG construction page

## Goal

Add a KG Studio construction workspace that lets users run the reusable
source-to-KG build workflow from the maintained React workbench. The page should
make the construction pipeline visible as source selection, build controls,
manifest/summary inspection, and a quick path back to candidate graph review.

## What I already know

- Backend runtime workflow already exists at `POST /api/kg/construction/build`.
- The API accepts explicit structured/manual source records or explicit TEP
  semantic-lift and variable-mapping artifact paths.
- The API writes `nodes.csv`, `edges.csv`, `kg_construction_summary.json`, and
  `kg_construction_manifest.json` under `runs/source_kg_build/<output_name>`.
- Existing KG Studio already has Overview, Sources, Graph, Review, and Draft Lab
  views, and can discover build directories through `/api/kg/studio`.
- Frontend stack is maintained under `web/`: React, TypeScript, Vite, Arco
  React, ECharts, React Router, and plain CSS tokens.

## Assumptions

- v0 does not need arbitrary file upload; local path and inline source text are
  acceptable for this research workbench.
- v0 should not publish directly to Neo4j from the browser. It should build
  candidate artifacts and refresh KG Studio inspection.
- The page should bias toward TEP merge workflows, but still support a manual
  structured record source so the pipeline is visibly reusable.

## Requirements

- Add a KG Studio "Build" route/tab.
- Add frontend API contracts and client method for
  `/api/kg/construction/build`.
- Provide compact build controls for:
  - output name;
  - overwrite toggle;
  - source type;
  - source id and scenario;
  - inline text/path inputs relevant to the selected source type;
  - TEP semantic-lift node/edge path pair;
  - TEP variable-mapping path.
- Show build status, output artifact paths, summary, and claim boundary.
- After a successful build, refresh KG Studio payload so Graph/Review can inspect
  the new candidate layer discovered by the backend.
- Keep layout consistent with RootLens workbench density and avoid nested card
  stacks.

## Acceptance Criteria

- [x] `/kg-studio/build` renders and is reachable from the KG Studio subnav.
- [x] A manual/structured source build can be submitted from the page.
- [x] A TEP semantic-lift or variable-mapping source request can be composed
  without invalid irrelevant fields.
- [x] Build response summary and artifact paths are visible.
- [x] Successful build triggers KG Studio refresh.
- [x] `cd web && npm run typecheck && npm run build` passes.

## Definition of Done

- Tests/checks pass for touched frontend.
- Docs are updated if user-facing KG Studio behavior changes.
- No new frontend dependencies.
- Backend KG construction semantics remain source-constrained and candidate-only.

## Out of Scope

- Browser file upload and persistent source library CRUD.
- Live LLM extraction provider selection.
- AST/code-file extraction.
- Direct Neo4j publication.
- Full human review workflow beyond existing KG Review/Draft tabs.

## Technical Notes

- Relevant frontend files:
  - `web/src/api/contracts.ts`
  - `web/src/api/client.ts`
  - `web/src/app/App.tsx`
  - `web/src/app/routes.tsx`
  - `web/src/state/app-state.ts`
  - `web/src/features/kg-studio/KGStudioPages.tsx`
- Relevant backend contract:
  - `src/kgtracevis/service/kg_construction.py`
- Relevant docs:
  - `docs/kg_construction.md`
  - `docs/source_to_kg_construction_system.md`

## Verification Notes

- `cd web && npm run typecheck` passed.
- `cd web && npm run build` passed with the existing Vite large chunk warning.
- Browser render smoke passed for `/kg-studio/build`.
- Direct latest-backend smoke for `POST /api/kg/construction/build` passed with
  the default manual CSV example and produced 2 nodes plus 1 candidate edge.
