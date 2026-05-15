# M12 KG construction artifact retrieval API

## Goal

Expose safe read access to source/material KG construction artifacts by stable
artifact key, so review, debug, artifact diff, and version comparison clients do
not need to trust raw filesystem paths.

## What I already know

* Construction summaries/manifests now share a stable artifact key map.
* Build records expose paths for nodes, edges, review queue, publish snapshots,
  manifests, review decisions, and `kg_construction_diff`.
* API clients can list builds and fetch review queues, but cannot fetch an
  arbitrary artifact by key.
* Run artifacts already use a safe filename-based endpoint; construction
  artifacts need a key-based endpoint because filenames and artifact keys are
  both meaningful.

## Requirements

* Add a service helper that resolves an artifact key for a known construction
  build without allowing path traversal.
* Add `GET /api/kg/construction/builds/{run_id}/artifacts/{artifact_key}`.
* Only allow keys from the construction artifact map plus `output_dir` if useful
  for metadata; do not accept raw paths or filenames with separators.
* Return actual files with `FileResponse`; reject directories and missing files
  with deterministic 404s.
* Support both source builds and material direct builds because they share the
  same construction manifest/artifact map.
* Add focused service/API tests for JSON, JSONL, and CSV artifacts plus invalid
  keys.

## Acceptance Criteria

* [ ] Build artifact endpoint returns `kg_construction_diff`, `review_queue`,
      `nodes`, and `review_decisions` for a generated build.
* [ ] Endpoint rejects unknown artifact keys and traversal-like keys.
* [ ] Endpoint works for a material direct build.
* [ ] Focused tests pass, then full quality gate passes.

## Out of Scope

* Artifact preview/rendering or pagination.
* Frontend UI wiring.
* Historical artifact storage beyond the current build directory.

## Technical Notes

* Use `kg_construction_artifact_paths(...)` and manifest `artifacts` mappings.
* Keep reusable logic under `src/kgtracevis/service/kg_construction.py`.
* API route belongs in `src/kgtracevis/service/api.py`.
