# M14 RCA KG construction acceptance smoke expansion

## Goal

Extend the RCA-KG construction acceptance smoke workflow so it verifies the
material-library direct build path in addition to toy generic and optional TEP
paths.

## Requirements

* Add a `material_direct` smoke path that uses a pre-extracted material record.
* The path must not require an LLM key or network access.
* It must run through `run_material_kg_construction_workflow(...)`, not through
  a handcrafted CSV export.
* It must validate the same required construction artifacts as the source
  workflow paths, including `kg_construction_diff.json`.
* Smoke CLI output should include the new path.

## Acceptance Criteria

* [ ] Smoke workflow reports `toy_generic`, `material_direct`, and optional
      `tep` paths.
* [ ] Material smoke metadata confirms material IDs, source IDs, required
      artifact count, and candidate edge count.
* [ ] Smoke CLI test covers the new path.
* [ ] Focused smoke tests pass, then full quality gate passes.

## Out of Scope

* Live document IE extraction.
* Frontend smoke testing.
