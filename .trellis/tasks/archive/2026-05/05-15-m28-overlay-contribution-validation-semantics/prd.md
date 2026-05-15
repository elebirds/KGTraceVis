# M28 Overlay Contribution Validation Semantics

## Goal

Fix the overly-strong `validated: true` signal in
`kg_overlay_validation_report.json`. Overlay validation should distinguish:

- CSV/import contract validity,
- runtime examples can execute,
- candidate overlay actually contributes to RCA paths/rankings.

## What I already know

- Current `run_kg_overlay_validation` writes `validated: true` whenever runtime
  analysis and import dry-run complete.
- A default material build validated against `data/examples` can report
  `validated: true` even when all examples have empty `kg_build_ids`.
- Runtime overlay smoke already proves contribution for a synthetic material
  example, so this task is about report semantics rather than path ranking.

## Requirements

- Add explicit report fields:
  - `contract_validated`
  - `runtime_validated`
  - `overlay_contributed`
  - `overlay_contribution_case_count`
  - `missing_overlay_contribution_warning`
- Preserve backward compatibility where useful, but make any aggregate
  `validated` field no stronger than contribution-aware validation.
- Include candidate build/source-edge contribution counts in the report.
- Update workflow, CLI/API tests, docs, and acceptance matrix.

## Acceptance Criteria

- [ ] A report over examples that do not use the candidate overlay has
  `contract_validated=true`, `runtime_validated=true`,
  `overlay_contributed=false`, and a warning.
- [ ] A report over a fixture that uses the candidate overlay has
  `overlay_contributed=true` and nonzero contribution counts.
- [ ] Service/API route returns the upgraded report.
- [ ] Focused and full quality gates pass.

## Out of Scope

- TEP runtime-level contribution smoke.
- Frontend review UI.
- Changing KG path ranking semantics.
