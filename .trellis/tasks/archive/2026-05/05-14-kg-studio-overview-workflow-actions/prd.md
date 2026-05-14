# Add KG Studio overview workflow actions

## Goal

Turn KG Studio Overview from a passive statistics page into a lightweight
workspace home. The page should expose clear next actions for source curation,
graph inspection, edge review, and draft adjustments while keeping the existing
read-only KG foundation.

## Requirements

- Add a workflow/action section to `/kg-studio/overview`.
- Include four action cards:
  - Sources: shows source/document counts and links to `/kg-studio/sources`.
  - Graph: shows candidate edge/node counts and links to `/kg-studio/graph`.
  - Review: shows review target/status context and links to `/kg-studio/review`.
  - Draft Lab: shows candidate edge context and links to `/kg-studio/drafts`.
- Use compact cards and AntD/icon buttons consistent with the existing dashboard.
- Do not add backend endpoints or mutate KG artifacts.
- Update documentation to describe Overview as a workflow hub.

## Acceptance Criteria

- Web build succeeds.
- Existing KG Studio/API tests pass.
- Browser verification confirms action cards render and navigation works.
- Full quality gates pass before commit.

## Out of Scope

- New metrics from backend.
- Direct KG editing or promotion.
- Remote LLM integrations.
