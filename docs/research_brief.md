# KGTraceVis Development Research Brief

Status: development reference, not a final experiment protocol.

Research date: 2026-05-01.

This document summarizes external papers and dataset documentation that can guide
KGTraceVis development before formal experiments are finalized. The goal is not
to claim settled ground truth, but to give implementation work a consistent
research-facing direction.

## Working Position

KGTraceVis should be developed as a knowledge-enhanced RCA pipeline over
structured anomaly evidence, not as another anomaly detector. The reusable
pipeline should connect:

```text
detector/adaptor output
-> unified evidence JSON
-> source-constrained KG
-> entity linking
-> consistency checking
-> correction candidates
-> RCA path ranking
-> visual review and feedback
```

This position is supported by three observations from the literature:

- Industrial KG research is still relatively early, with gaps around empirical
  validation and industrial application, so a small reproducible KG pipeline is a
  reasonable research contribution.
- RCA in manufacturing benefits from combining expert knowledge, graph
  reasoning, and human feedback instead of relying only on data-driven methods.
- Visual analytics papers emphasize that anomaly detection is often only the
  first step; analysts still need tooling for hypothesis generation and root
  cause reasoning.

## Dataset Implications

### MVTec / DS-MVTec

MVTec AD provides industrial anomaly images with defect-free training images,
test images, and pixel-precise anomaly masks. The official download page lists
15 categories including bottle, cable, capsule, metal nut, pill, and screw.

Defect Spectrum extends several industrial defect datasets with richer semantic
annotations. Its DS-MVTec layout contains image, caption, mask, and rgb_mask
folders for MVTec-style categories. This makes it useful for converting visual
defects into evidence fields such as `anomaly_type`, `location`,
`morphology`, and `severity`.

Development decision:

- Use MVTec / DS-MVTec for visual evidence extraction and curated plausible RCA.
- Do not claim that MVTec has native factory root-cause labels.
- Build a manual RCA reference layer for selected categories.
- Treat that layer as `review_status=reviewed` or `review_status=auto`
  depending on how carefully the mapping was curated.

Recommended first categories:

- `metal_nut`
- `cable`
- `screw`
- `bottle`
- `capsule`
- `pill`

Recommended root-cause categories:

- `MechanicalContact`
- `HandlingDamage`
- `AssemblyError`
- `MaterialDefect`
- `Contamination`
- `MissingComponent`
- `SurfaceWear`
- `ProcessMisalignment`
- `PackagingPressure`

### Tennessee Eastman Process

The Tennessee Eastman Process is a classic simulated industrial chemical
process benchmark for process control and fault diagnosis. Development should
use it as the cleanest quantitative RCA scenario because faults, process
variables, and process units can be mapped into a structured KG.

Development decision:

- Use TEP for variable-to-unit and unit-to-fault path ranking.
- Prefer small curated mappings first, then expand.
- Evaluate top-k RCA path accuracy and MRR when a clear fault label or fault
  type mapping is available.

### Wafer

The wafer use case should remain the most realistic visual analytics case study:
image evidence plus log events plus process KG paths. It should not be forced
into large-scale quantitative RCA unless reliable ground-truth labels are
available.

Development decision:

- Use wafer for multimodal case studies and demo workflows.
- Keep every log-event and process-cause edge source-constrained.
- Prefer expert acceptance rate, path plausibility, and case-study analysis when
  labels are incomplete.

## Method Implications

### Source-Constrained KG

KG edges should remain small and auditable. Every edge must preserve:

```text
source
evidence
confidence
weight
review_status
feedback_count
accepted_count
rejected_count
```

The KG should support task operations rather than become a large general
industrial ontology:

- normalize evidence fields,
- detect inconsistent fields,
- generate correction candidates,
- rank RCA paths,
- show paths and source edges in the UI,
- accept or reject feedback.

### Entity Linking

Use deterministic linking before any LLM fallback:

1. exact ID,
2. exact name,
3. alias,
4. fuzzy match,
5. embedding or LLM-assisted candidate only if needed later.

Low-confidence matches should be recorded as ambiguous, not silently accepted.

### Consistency Checking

Initial constraints should be relation-based and explainable:

```text
anomaly_type -> morphology
anomaly_type -> location
anomaly_type -> log_event
variable -> process_unit
fault_type -> root_cause
```

This supports a simple but defensible score:

```text
consistency_score = entity_linking_score + relation_constraint_score
```

The score should be described as a lightweight deterministic score, not learned
industrial truth.

### RCA Path Ranking

Keep the documented relation-weighted path scoring:

```text
Score(P) = alpha * Conf(P) + beta * EvidenceMatch(P) - gamma * Length(P)
```

Each returned path should expose:

- stable `path_id`,
- nodes,
- relations,
- score,
- supporting evidence,
- source edges.

This matches the project goal of traceability and visual review.

### Human Feedback

The literature supports interactive RCA workflows where domain experts can
update or correct the graph. KGTraceVis should keep this as a lightweight
review layer in v0:

- accept/reject correction candidate,
- accept/reject RCA path,
- edit evidence field,
- accept/reject KG edge.

Do not describe confidence updates as complex online learning.

## Development Backlog From Research

Priority 1:

- Create `docs/mvtec_rca_annotation_guide.md`.
- Add `data/kg/mvtec_rca_reference.csv` or an equivalent curated edge file.
- Expand the in-memory KG loader to merge scenario-specific CSVs.
- Add tests for noisy visual evidence correction.

Priority 2:

- Add TEP variable-unit-fault mappings.
- Implement metrics for top-k RCA accuracy and MRR.
- Create reproducible noise experiment scripts.

Priority 3:

- Rebuild the future RootLens dashboard against the FastAPI backend for
  evidence, linked entities, conflicts, corrections, and RCA paths.
- Add feedback records and deterministic confidence updates.
- Add Neo4j import/query parity after the in-memory pipeline is stable.

## Sources

- [MVTec AD official download documentation](https://www.mvtec.com/company/research/datasets/mvtec-ad/downloads?cHash=a79aa4ef833d7bfed981e2fba6342c8f&gad_source=1)
- [MVTec AD paper](https://link.springer.com/article/10.1007/s11263-020-01400-4)
- [Defect Spectrum arXiv paper](https://arxiv.org/abs/2310.17316)
- [Defect Spectrum Hugging Face dataset page](https://huggingface.co/datasets/DefectSpectrum/Defect_Spectrum)
- [Tennessee Eastman process original reference](https://users.abo.fi/~khaggblo/RS/Downs.pdf)
- [Extended Tennessee Eastman dataset paper](https://www.sciencedirect.com/science/article/pii/S0098135421000594)
- [Knowledge Graphs in Manufacturing and Production survey](https://arxiv.org/abs/2012.09049)
- [Industrial RCA using Knowledge Graphs](https://www.sciencedirect.com/science/article/pii/S1877050922003015)
- [Interactive RCA with Bayesian Networks and Knowledge Graphs](https://arxiv.org/abs/2402.00043)
- [PIXAL anomaly reasoning visual analytics](https://arxiv.org/abs/2205.11004)
