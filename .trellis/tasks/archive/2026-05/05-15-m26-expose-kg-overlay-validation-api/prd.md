# M26 Expose KG Overlay Validation API

## Goal

Expose the candidate KG overlay validation workflow through the construction
service/API so users and future KG Studio UI can validate a build's runtime RCA
readiness without shelling out to `scripts/validate_kg_overlay.py`.

## Scope

- Add service DTOs and helper for build-scoped overlay validation.
- Add a FastAPI route under `/api/kg/construction/builds/{run_id}/...`.
- Reuse `kgtracevis.workflows.kg_overlay_validation`; do not duplicate runtime
  validation logic in service handlers.
- Write the same `kg_overlay_validation_report.json` artifact beside the build.
- Keep validation read-only with respect to construction, review decisions, and
  Neo4j publication.
- Add focused service/API tests and docs.

## Acceptance

- API route returns build metadata, report payload, and report path.
- The report includes RCA runtime metadata and import dry-run counts.
- Missing build IDs return 404 and validation errors return 400.
- Focused tests plus full quality gates pass.
