# Split KG Studio sources into focused workspaces

## Goal

Make the KG Studio Sources page read like a real source management workspace
instead of a dense mixed panel. Separate source registry browsing, source
document browsing, and Source-to-KG candidate extraction into focused tabs
within the Sources area while preserving the existing API contracts and
non-mutating KG workflow.

## Requirements

- Keep `/kg-studio/sources` as the top-level KG Studio menu entry.
- Add focused in-page tabs for:
  - Source Registry: source registry search, summary count, and source rows.
  - Source Documents: document search, summary count, and document rows.
  - Extract Draft: Source-to-KG draft generator and candidate edge result table.
- Search state should remain local to Sources and apply to the registry/document
  tabs without affecting Graph/Review/Draft filters.
- The extract tab should not show the registry/document browser around it; the
  candidate generation form needs enough horizontal space to read evidence.
- Do not mutate candidate KG CSVs or tracked `data/kg/` files.
- Update dashboard documentation for the nested Sources tabs.

## Acceptance Criteria

- Web build succeeds.
- Existing KG Studio/API tests pass.
- Browser verification confirms the three Sources tabs, source/document search,
  and Source-to-KG candidate table still work.
- Project quality gates still pass before commit.

## Out of Scope

- New backend endpoints.
- Remote LLM extraction.
- Direct KG promotion or mutation.
