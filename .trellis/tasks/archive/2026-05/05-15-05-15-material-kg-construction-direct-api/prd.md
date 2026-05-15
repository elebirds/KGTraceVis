# M11 material KG construction direct workflow API

## Goal

Make material-library selected builds a first-class RCA-KG construction path:
users select uploaded/registered materials and the backend directly runs the
material extraction/build workflow into the same artifact-complete construction
outputs as source-library builds.

## What I already know

* `run_material_kg_construction_workflow(...)` exists and can extract selected
  materials when a fake or OpenAI-compatible IE client is supplied.
* The service API currently exposes `/api/kg/materials/build-sources`, which
  returns a construction request; callers then invoke `/api/kg/construction/build`
  separately.
* M10 added `kg_construction_diff.json` and `diff_path` to source builds.
* Material workflow results currently expose only a small subset of the source
  build artifact envelope, and the persisted construction manifest is not
  refreshed with material-library metadata.

## Requirements

* Add a direct material build API route that calls the reusable material
  construction workflow.
* Keep `/api/kg/materials/build-sources` for compatibility.
* Expose artifact-complete material workflow results, including source library,
  layer manifests, review queue, publish manifest, and `kg_construction_diff`.
* Persist material-library metadata into both summary and construction manifest.
* Preserve claim boundaries: extracted/material-derived KG rows remain
  candidate/reviewable facts and do not publish automatically.
* Support pre-extracted materials without requiring an LLM key.
* Support extraction-mode plumbing for workflow clients; API can default to
  `never` to avoid accidental live LLM/network dependency.

## Acceptance Criteria

* [ ] `POST /api/kg/materials/build` runs selected extracted materials through
      the material workflow and returns artifact paths/counts.
* [ ] Direct material build response includes `diff_path`, review queue path,
      publish snapshot paths, source library manifest path, and layer manifest
      paths.
* [ ] `kg_construction_summary.json` and `kg_construction_manifest.json` both
      include a `material_library` section.
* [ ] Pre-extracted material build route works without an LLM key.
* [ ] Existing build-sources route continues to work.
* [ ] Focused service/workflow tests pass, then full quality gate passes.

## Out of Scope

* Frontend UI wiring for the direct material build route.
* Live browser/web extraction UX.
* Neo4j publish from material builds.
* OpenAI key management or model selection UI.

## Technical Notes

* Reuse `src/kgtracevis/workflows/material_kg_construction.py`.
* API wiring lives in `src/kgtracevis/service/api.py`.
* Service DTO shape should stay frontend-friendly and avoid leaking huge source
  chunk text.
* Required artifact keys remain the shared construction artifact map.
