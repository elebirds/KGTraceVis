# RootLens KG Force Graph And Draft Review

## Goal

Make the KG Studio look and behave like the beginning of human-in-the-loop graph
management: reviewers can inspect candidate KG edges in a force-directed graph
preview, select edges visually, and write append-only draft adjustment records
without mutating tracked KG CSVs.

## Requirements

### Frontend

1. Add a force-directed SVG graph preview for candidate KG nodes/edges.
2. Selecting an edge in the force graph must sync with the existing KG edge
   inspector and review target.
3. Preserve the existing list view as a scan-friendly fallback/companion.
4. Add a draft adjustment form for the selected edge with:
   - draft action (`keep`, `revise`, `reject`, `promote_later`);
   - optional proposed relation;
   - optional proposed evidence text;
   - optional proposed confidence;
   - notes.
5. Keep the UI non-mutating and explicit about draft-only behavior.

### Backend/API

1. Add append-only draft storage under `runs/kg_studio_drafts/`.
2. Add `POST /api/kg/drafts` to record one KG edge draft adjustment.
3. Validate that draft confidence, when provided, is in `[0, 1]`.
4. Return the recorded draft with a stable `draft_id`.
5. Do not modify candidate KG CSVs or tracked `data/kg/` files.

### Documentation And Smoke

1. Update dashboard docs with force graph and draft behavior.
2. Extend smoke test to submit one draft adjustment.
3. Run Python/frontend quality gates.

## Out of Scope

- Promotion into tracked KG files.
- Collaborative conflict resolution.
- LLM source-to-KG extraction UI.
- Full arbitrary node/edge creation.

## Acceptance Criteria

- [ ] KG Studio displays a force-directed graph preview when candidate edges are
  available.
- [ ] Edge selection syncs between graph/list/inspector.
- [ ] Draft adjustment submissions persist as JSONL under `runs/kg_studio_drafts/`.
- [ ] Draft submission does not mutate KG CSVs.
- [ ] Quality gates pass.

