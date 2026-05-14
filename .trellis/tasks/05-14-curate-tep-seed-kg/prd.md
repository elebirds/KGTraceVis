# brainstorm: curate TEP seed KG

## Goal

Implement a curated seed knowledge graph layer for the TEP dataset by referencing KGTraceVis, the sibling RootLens project, and the sibling TEP_KG project under `~/code/`. The result should make TEP runtime reasoning usable while preserving KGTraceVis source-constrained, reviewable KG rules.

## What I already know

* KGTraceVis currently has populated MVTec and wafer seed KG layers.
* `data/kg/tep_nodes.csv` and `data/kg/tep_edges.csv` currently contain only headers.
* The shared `data/kg/nodes.csv` and `data/kg/edges.csv` include a tiny example TEP layer.
* KG CSV edges must include `source`, `evidence`, `confidence`, `weight`, `review_status`, and feedback counters.
* TEP seed KG should support entity linking, consistency checking, correction candidates, and path ranking without claiming unsupported verified causality.

## Assumptions (temporary)

* The first implementation should stay small and curated rather than importing a large external ontology wholesale.
* Source material from sibling projects may be used as project-local provenance, but claims still need conservative confidence and review status.
* TEP fault-to-root-cause links should be framed as plausible/reference labels unless the source clearly supports stronger language.

## Open Questions

* None for this seed implementation.

## Requirements (evolving)

* Populate TEP seed node and edge CSV files with schema-valid rows.
* Keep KG rows scenario-scoped as `tep` unless a row is truly shared.
* Add enough aliases to support producer/adaptor mentions such as TEP variables and fault labels.
* Preserve source-constrained provenance on every edge.
* Avoid overwriting or weakening existing MVTec/wafer behavior.
* Avoid generic process-to-variable support edges that create RCA shortcut leakage.

## Acceptance Criteria (evolving)

* [x] `data/kg/tep_nodes.csv` contains curated TEP nodes beyond the header.
* [x] `data/kg/tep_edges.csv` contains curated TEP edges beyond the header.
* [x] `uv run python scripts/build_kg.py --nodes data/kg/tep_nodes.csv --edges data/kg/tep_edges.csv` passes.
* [x] Default KG validation/import dry run includes the TEP layer.
* [x] Existing tests or focused KG tests pass for the changed contracts.

## Definition of Done (team quality bar)

* Tests added/updated if needed.
* Lint / typecheck / relevant tests green where practical.
* Docs/notes updated if behavior changes.
* Rollout/rollback considered if risky.

## Out of Scope (explicit)

* No large general-purpose industrial KG.
* No automatic promotion of candidate extraction output to reviewed truth.
* No full TEP causal discovery implementation.
* No Neo4j mutation during implementation; only seed files and code/docs as needed.

## Technical Notes

* Task directory: `.trellis/tasks/05-14-curate-tep-seed-kg/`
* Relevant local files: `data/kg/tep_nodes.csv`, `data/kg/tep_edges.csv`, `src/kgtracevis/kg/graph.py`, `scripts/build_kg.py`.
* Used `/Users/hhm/code/TEP_KG/data/processed/kg/tep_variable_mapping.jsonl` for XMEAS/XMV aliases.
* Used `/Users/hhm/code/TEP_KG/data/processed/rca/fault_root_cause_labels.json` for IDV(1-19) fault anchors.
* Used RootLens runtime/build scripts as a cross-check that Fault 06 aligns with stream-1 A-feed loss, XMEAS_1, and XMV_3.
* Verification passed: focused KG validation, default KG validation, dry-run import, `scripts/run_examples.py`, ruff, and full pytest.
