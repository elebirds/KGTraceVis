# M31 KG Studio Construction Review Acceptance

## Goal

Close the remaining acceptance-matrix gap that KG construction review is proven
through CLI/API artifacts but not through the maintained KG Studio frontend.

## Scope

- Add TypeScript contracts and API client helpers for construction build
  registry, review queue, review action, and overlay validation.
- Extend the KG Studio build view with a compact construction review workspace:
  select a build, load review queue, accept/reject the selected candidate, and
  run overlay validation.
- Preserve claim boundaries: UI actions review candidate build artifacts only;
  they do not publish to Neo4j or mark LLM output as ground truth.
- Keep the workbench dense and feature-scoped under `web/src/features/kg-studio`.
- Update acceptance docs once the UI contract is wired and typechecked.

## Non-Goals

- Do not build a full bespoke visual review application.
- Do not modify `web_legacy/`.
- Do not run real Neo4j import from the UI.
- Do not certify live LLM extraction quality.

## Acceptance Criteria

- KG Studio can list construction builds and load a selected build's
  `review_queue.json` via `/api/kg/construction/builds/{run_id}/review-queue`.
- KG Studio can submit accept/reject decisions via
  `/api/kg/construction/builds/{run_id}/review` and refresh the queue.
- KG Studio can run `/validate-overlay` and expose `validated`,
  `overlay_contributed`, and warning/report fields to the analyst.
- `cd web && npm run typecheck` and `cd web && npm run build` pass.
- Backend tests touched by contract changes still pass.

## Audit Status

This turns the previous "UI review pages can consume API/report contracts" note
from a remaining non-goal into an explicit workbench acceptance row.
