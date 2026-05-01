# AGENTS.md

This file provides instructions for AI coding agents and human contributors
working on KGTraceVis.

## 1. Project Goal

KGTraceVis is a research prototype for knowledge-enhanced industrial anomaly
detection and root-cause traceability.

The system converts heterogeneous anomaly outputs from images, process time
series, and wafer logs into a unified anomaly evidence JSON schema. It then uses
a source-constrained industrial knowledge graph to perform:

1. entity linking,
2. evidence consistency scoring,
3. noisy evidence correction,
4. relation-weighted root-cause path ranking,
5. visual analytics,
6. optional human feedback capture.

The project supports a research paper and visual analytics prototype. Prioritize
clarity, reproducibility, and traceability over complex model design.

## 2. Core Design Principles

### 2.1 Do Not Build a Giant General-Purpose KG

The KG is task-oriented. Only add nodes and edges that support at least one of:

- evidence normalization,
- consistency checking,
- correction candidate generation,
- root-cause path ranking,
- visual analytics explanation,
- human feedback review.

### 2.2 Never Add Unsupported Industrial Facts

Do not invent causal relations.

Every KG edge must include:

- `source`
- `evidence`
- `confidence`
- `review_status`

If the source is uncertain, set a lower confidence and mark
`review_status=auto`.

### 2.3 Keep the Three Use Cases Separate but Schema-Compatible

Supported scenarios:

- `mvtec`
- `tep`
- `wafer`

Each scenario may have its own subgraph, but all subgraphs must use the shared
ontology schema.

### 2.4 LLMs Are Adapters, Not Authorities

LLM-based extraction may generate candidate entities or triples, but the output
must be:

- schema-validated,
- source-attached,
- confidence-scored,
- editable,
- never treated as ground truth by default.

## 3. Repository Structure

Use one uv-managed Python package. Do not introduce a uv workspace unless the
repository later contains multiple independently maintained packages.

Expected structure:

```text
src/kgtracevis/
├── core/
├── schema/
├── adapters/
├── kg_construction/
├── kg/
├── mask/
├── noise/
├── metrics/
├── viz/
├── feedback/
├── service/
└── app/
```

Top-level directories should stay limited to:

```text
configs/
src/
scripts/
data/
runs/
outputs/
artifacts/
notebooks/
docs/
paper/
tests/
```

Do not create new top-level directories unless necessary.

## 4. Script-System Separation

Do not place core analysis logic directly inside scripts, notebooks, Streamlit
files, or future service handlers.

Reusable logic must live under `src/kgtracevis/`.

Scripts and apps are clients. They may parse arguments, load config, call the
core pipeline, and save outputs. They must not duplicate entity linking,
consistency checking, correction generation, path ranking, noise injection, or
metric logic.

Preferred dependency direction:

```text
scripts/        -> src/kgtracevis/
app/service     -> src/kgtracevis/
notebooks/      -> src/kgtracevis/
src/kgtracevis/ -> no dependency on scripts/notebooks/app UI state
```

## 5. Human Feedback Compatibility

Do not build a full human-in-the-loop system in v0, but keep outputs
feedback-compatible.

When implementing correction or path ranking modules:

- return stable IDs for correction candidates,
- return stable IDs for ranked paths,
- include enough source edge information for review,
- avoid anonymous lists that cannot be referenced later.

Feedback records should support at least:

- correction feedback,
- path feedback,
- entity linking feedback,
- KG edge feedback.

KG edge CSV files must include feedback counters:

- `feedback_count`
- `accepted_count`
- `rejected_count`

The initial confidence update rule may be lightweight and deterministic. Do not
describe it as complex online learning.

## 6. Coding Standards

- Use Python 3.10+.
- Use uv for dependency management and lockfile generation.
- Use type hints where practical.
- Use Pydantic for JSON schema validation.
- Use `neo4j` Python driver for Neo4j access.
- Prefer small, testable functions.
- Avoid hidden global state.
- Avoid hard-coded absolute paths.
- Read paths from `configs/paths.yaml` or environment variables.
- Write docstrings for public functions.

## 7. Evidence JSON Rules

All dataset adapters must output the unified anomaly evidence schema.

Required top-level fields:

- `case_id`
- `dataset`
- `source`
- `object`
- `anomaly_type`
- `location`
- `morphology`
- `severity`
- `confidence`
- `timestamp`
- `raw_evidence`
- `normalized_evidence`
- `kg_analysis`

Optional feedback-compatible field:

- `human_feedback`

If a field is unknown, use `null` or `"unknown"` consistently.

Do not create dataset-specific JSON schemas unless explicitly required.
Dataset-specific information should go inside `raw_evidence`.

## 8. KG CSV Rules

Nodes must follow:

```csv
id,name,label,scenario,aliases,description
```

Edges must follow:

```csv
head,relation,tail,scenario,source,evidence,confidence,weight,review_status,feedback_count,accepted_count,rejected_count
```

Rules:

- `id` should use PascalCase, e.g. `ScratchDefect`.
- Relation names should use uppercase snake case, e.g. `HAS_MORPHOLOGY`.
- `scenario` must be one of `mvtec`, `tep`, `wafer`, or `shared`.
- `confidence` must be a float in `[0, 1]`.
- `weight` should normally be `1 - confidence`.
- `review_status` should be one of `auto`, `reviewed`, `rejected`.
- Feedback counters must be non-negative integers.
- Do not overwrite reviewed triples automatically.

## 9. Source-Constrained KG Construction

When implementing candidate extraction:

1. Extract candidate entities and triples only from provided sources.
2. Store the exact source text or table row in the `evidence` field when possible.
3. Assign confidence based on source type:
   - dataset label / official table: high confidence,
   - prior project / thesis text: medium-high confidence,
   - LLM extraction from text: medium or low confidence,
   - common industrial heuristic: low confidence.
4. Do not overwrite reviewed triples automatically.
5. Deduplicate nodes by `id`, aliases, and normalized lowercase names.
6. Register source references in `data/kg/source_registry.csv` or `docs/sources/`.

## 10. Entity Linking Rules

Entity linking should use:

1. exact ID match,
2. exact name match,
3. alias match,
4. fuzzy match,
5. optional embedding or LLM-assisted match only as fallback.

Return top-k candidates with scores. Do not silently choose a low-confidence
candidate without recording ambiguity.

## 11. Consistency Checking Rules

The consistency checker should compare evidence fields against KG constraints,
including:

- `anomaly_type` vs `morphology`,
- `anomaly_type` vs `location`,
- `variable` vs `process_unit`,
- `log_event` vs `fault_event`,
- `fault_event` vs `root_cause`.

Return:

- `consistency_score`,
- `inconsistent_fields`,
- `correction_candidates`.

Do not mutate the original evidence directly. Store corrected output separately
under `normalized_evidence` or `kg_analysis`.

## 12. Path Ranking Rules

Path ranking should not rely only on shortest path.

Use a relation-weighted score:

```text
Score(P) = alpha * Conf(P) + beta * EvidenceMatch(P) - gamma * Length(P)
```

Where:

- `Conf(P)` uses edge confidence,
- `EvidenceMatch(P)` measures overlap with linked evidence entities,
- `Length(P)` penalizes overly long paths.

Return top-k paths with:

- stable `path_id`,
- node sequence,
- relation sequence,
- score,
- supporting evidence,
- source edges.

## 13. Noise Injection Rules

Noise should be field-level and reproducible.

Supported noise types:

- anomaly type replacement,
- location replacement,
- morphology replacement,
- variable deletion,
- variable name perturbation,
- log event deletion,
- synonym substitution,
- contradiction injection.

Always record:

- `is_noisy`,
- `noise_level`,
- `corrupted_fields`,
- `clean_reference`.

Use fixed random seeds for experiments.

## 14. Metrics Rules

Implement metrics as standalone functions.

Required metrics include:

- schema validity rate,
- entity linking accuracy,
- top-k linking accuracy,
- inconsistency detection precision/recall,
- correction accuracy,
- top-k correction accuracy,
- noise recovery rate,
- top-k root-cause accuracy,
- MRR,
- path hit rate.

Do not mix metric computation with visualization code.

## 15. Visual Analytics App Rules

The demo app should show:

1. raw evidence,
2. normalized evidence,
3. linked KG entities,
4. consistency score,
5. inconsistent fields,
6. correction candidates,
7. top-k paths,
8. optional what-if editing,
9. optional human feedback actions.

The app should be lightweight and runnable locally with Streamlit.

## 16. Testing Requirements

Before submitting code changes, run:

```bash
uv run --extra dev pytest
uv run python scripts/run_examples.py
```

If Neo4j-related code is modified, also run:

```bash
uv run python scripts/import_kg.py
uv run python scripts/run_examples.py --with-neo4j
```

Tests should cover:

- schema validation,
- KG CSV loading,
- entity linking,
- consistency checking,
- path ranking,
- noise injection,
- metric calculation.

## 17. Documentation Requirements

When adding a new module, update:

- README.md if user-facing behavior changes,
- docs/project_design.md if architecture changes,
- docs/ontology_schema.md if KG schema changes,
- docs/evidence_schema.md if JSON schema changes.

## 18. Notebook Rules

Notebooks are for exploration only.

- Do not define key functions in notebooks.
- Move reusable logic into `src/kgtracevis/`.
- Formal experiments must be implemented in `scripts/`.
- Do not rely on notebook output state for reproducibility.

## 19. Paper and Output Rules

Generate experiment artifacts under `runs/`, `outputs/`, or `artifacts/`.

Stable, selected paper assets may be copied into:

```text
paper/figures/
paper/tables/
```

Record how paper figures and tables were generated. Do not commit LaTeX build
artifacts.

## 20. What Not To Do

Do not:

- claim MVTec has real root-cause labels,
- treat possible causes as verified causes,
- add unsupported industrial causal edges,
- train unnecessary deep models for v0,
- create dataset-specific schema variants,
- silently discard low-confidence or ambiguous KG matches,
- remove `source`, `evidence`, `confidence`, or `review_status` from KG edges,
- put large raw datasets into Git,
- put experiment runs or generated outputs into Git,
- duplicate core pipeline logic in scripts, notebooks, Streamlit, or service files.

## 21. Preferred Development Order

1. pyproject.toml + uv.lock
2. README.md + AGENTS.md
3. directory structure
4. evidence schema
5. example JSON
6. nodes.csv / edges.csv minimal examples
7. import_neo4j.py
8. entity_linker.py
9. consistency_checker.py
10. path_ranker.py
11. noise_injector.py
12. metrics
13. Streamlit demo
14. dataset adapters
15. experiments

Prioritize a working v0 pipeline over completeness.
<!-- TRELLIS:START -->
# Trellis Instructions

These instructions are for AI assistants working in this project.

This project is managed by Trellis. The working knowledge you need lives under `.trellis/`:

- `.trellis/workflow.md` — development phases, when to create tasks, skill routing
- `.trellis/spec/` — package- and layer-scoped coding guidelines (read before writing code in a given layer)
- `.trellis/workspace/` — per-developer journals and session traces
- `.trellis/tasks/` — active and archived tasks (PRDs, research, jsonl context)

If a Trellis command is available on your platform (e.g. `/trellis:finish-work`, `/trellis:continue`), prefer it over manual steps. Not every platform exposes every command.

If you're using Codex or another agent-capable tool, additional project-scoped helpers may live in:
- `.agents/skills/` — reusable Trellis skills
- `.codex/agents/` — optional custom subagents

## Subagents

- ALWAYS wait for all subagents to complete before yielding.
- Spawn subagents automatically when:
  - Parallelizable work (e.g., install + verify, npm test + typecheck, multiple tasks from plan)
  - Long-running or blocking tasks where a worker can run independently.
  - Isolation for risky changes or checks

Managed by Trellis. Edits outside this block are preserved; edits inside may be overwritten by a future `trellis update`.

<!-- TRELLIS:END -->
