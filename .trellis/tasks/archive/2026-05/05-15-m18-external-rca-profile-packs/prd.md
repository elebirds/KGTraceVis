# M18 External RCA Profile Domain Packs

## Goal

Move RCA domain/profile policy from Python-only built-ins toward external,
auditable Domain Pack files. A construction build should be able to load a JSON
RCA profile, use it for semantic projection and RCA view defaults, and write a
profile manifest artifact so the build is reproducible.

## Scope

- Add JSON profile loading and validation under `src/kgtracevis/kg_construction/`.
- Preserve built-in generic and TEP profiles as defaults.
- Allow workflows and service build requests to pass a `profile_path`.
- Write `profile_manifest.json` as a stable construction artifact.
- Include profile manifest content in summaries/manifests and diff snapshots.
- Add focused tests for profile loading and workflow/API artifact propagation.
- Add tracked example profile packs under `configs/`.

## Non-Goals

- Do not introduce a YAML dependency in this slice.
- Do not implement a full projection DSL yet.
- Do not change the CSV node/edge base contract.
- Do not publish external profile candidates as reviewed facts.

## Acceptance

- `run_kg_construction(...)` still works with no profile path.
- A JSON profile path can rewrite/swap semantic relations and configure RCA
  family defaults.
- Every build writes `profile_manifest.json`.
- Summary and construction manifest expose the new artifact key.
- Existing smoke builds still pass for toy generic, material direct, and TEP.
