# Paper Section 5 Acceptance Guide

This guide is the backend-side acceptance entry for RootLens Section 5.

It does **not** redefine the product workflow. Instead, it explains how to use
existing KGTraceVis backend-mode assets to verify whether Section 5 claims are
supported by the real system.

## Acceptance command

Build a reproducible acceptance bundle:

```bash
uv run python scripts/build_rootlens_phase4_acceptance_bundle.py --overwrite
```

Default output:

```text
runs/rootlens_phase4_acceptance/
```

## Bundle structure

The acceptance bundle writes:

- `manifest.json` — machine-readable summary for Sections 5.1 / 5.2 / 5.3
- `notes.md` — top-level bundle notes
- `paper_section5_acceptance.md` — generated section-status snapshot
- `section_5_1/` — evidence overview and detection-detail backend assets
- `section_5_2/` — reasoning-view backend assets
- `section_5_3/` — provenance / feedback / materials backend assets

Each section directory includes JSON payloads captured from real backend-mode
API flows plus a section-specific `notes.md` describing:

- recommended frontend route(s)
- run/material/draft context
- suggested screenshot targets
- exact backend payload files to inspect

## How to use it

1. Run the acceptance-bundle script.
2. Inspect `manifest.json`.
3. For each section:
   - open the corresponding `notes.md`
   - use the referenced route/context in RootLens backend mode
   - verify the screenshot or walkthrough against the saved JSON payloads
4. If a claim cannot be supported by the saved backend assets, mark it as
   **partial** and shrink the paper wording instead of introducing new logic in
   the acceptance phase.

## Status semantics

- `supported` — the backend bundle contains a complete chain for that claim
- `partial` — the backend bundle contains only partial support; the paper should
  use weaker wording

## Boundaries

This phase is intentionally backend-only:

- no new reasoning logic
- no new construction logic
- no automatic screenshot generation
- no mutation of tracked KG files

The goal is to make backend-mode support for Section 5 **auditable and
repeatable**, not to expand product scope.
