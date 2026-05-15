# M19 RCA Reasoning Scoring Schema

## Goal

Upgrade the RCA reasoning view from "propagation edge annotations" to a more
explicit, profile-driven scoring graph contract. Each RCA edge should carry
stable score components so downstream path ranking and visual explanation can
understand why an edge is strong or weak.

## Scope

- Extend relation-family policy with scoring weights for confidence, priority,
  attenuation, and source trust.
- Compute per-edge RCA score components in the reasoning view.
- Preserve source/import metadata overrides without treating candidates as
  reviewed facts.
- Export scoring policy and score summaries in `rca_view_manifest.json`.
- Keep the base KG CSV contract stable; scoring details should live in optional
  RCA columns or metadata-compatible fields.
- Add tests for default policy, external profile policy, and TEP smoke safety.

## Non-Goals

- Do not replace the existing runtime root-cause path ranker in this slice.
- Do not train or learn edge weights.
- Do not infer unsupported causal facts.
- Do not make LLM output reviewed or canonical.

## Acceptance

- RCA view edges expose deterministic scoring components.
- Profile JSON can configure family-level scoring weights.
- Manifest records the scoring policy used for each relation family.
- Existing toy generic, material direct, and TEP construction smokes still pass.
