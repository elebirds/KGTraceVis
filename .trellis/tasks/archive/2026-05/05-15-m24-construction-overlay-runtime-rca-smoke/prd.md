# M24 Construction Overlay Runtime RCA Smoke

## Goal

Add an acceptance smoke that proves a source-to-KG construction output can be
loaded as a runtime candidate KG overlay and used by generic RCA path ranking,
including RCA score/path strength and `kg_build_id` provenance.

## Scope

- Extend construction smoke with a runtime overlay validation step.
- Use a small toy source/evidence pair so the test does not depend on Neo4j.
- Verify runtime top-k path uses constructed edge metadata.
- Keep existing toy/material/TEP construction smoke behavior.

## Non-Goals

- Do not add a frontend test.
- Do not publish to Neo4j.
- Do not change source extraction behavior.

## Acceptance

- Smoke summary reports the runtime overlay validation.
- Runtime path contains constructed `kg_build_id`, `path_strength`, and
  supporting source edge metadata.
- Full tests and smoke remain green.
