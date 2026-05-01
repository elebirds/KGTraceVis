# MVTec RCA Annotation Guide

Status: development reference, not final ground truth.

Research date: 2026-05-01.

MVTec AD and DS-MVTec can support KGTraceVis RCA development only after manual
augmentation. The original MVTec data provides visual defect categories and
pixel-level anomaly masks, but it does not provide verified factory root causes.
Therefore, this guide defines a curated plausible RCA reference layer.

## Scope

Use the reference layer to answer:

```text
Given a visual defect evidence object, can KGTraceVis recover a plausible,
source-traceable RCA path?
```

Do not use it to claim:

```text
This MVTec sample truly occurred because of this factory process cause.
```

## Recommended Object Classes

Start with object categories where visual defects have intuitive manufacturing,
handling, assembly, or contamination interpretations:

| Object | Why useful for RCA development |
|---|---|
| `metal_nut` | scratches, color changes, bent/deformed shapes can map to surface contact, wear, handling, or process misalignment |
| `cable` | missing/cut/bent cable features can map to assembly or cutting faults |
| `screw` | surface scratches and manipulated pose-like defects can map to handling, wear, or assembly issues |
| `bottle` | contamination or broken defects can map to contamination, molding, or transport damage |
| `capsule` | cracks, squeeze, and contamination can map to material, packaging, or pressure causes |
| `pill` | cracks, contamination, and deformation can map to material, coating, or packaging causes |

Avoid starting with texture classes unless the annotation target is only surface
defect semantics, because root-cause categories are harder to defend.

## Root-Cause Taxonomy V0

Keep the taxonomy small. Expand only when annotations require it.

| Root cause ID | Meaning | Typical visual evidence |
|---|---|---|
| `MechanicalContact` | Local physical contact with another object or tool | scratch, gouge, scrape, linear mark |
| `HandlingDamage` | Damage introduced during handling, transport, or manual manipulation | scratch, dent, broken, bent |
| `AssemblyError` | Incorrect assembly, missing part, misplacement, wrong orientation | missing wire, bent wire, manipulated component |
| `MaterialDefect` | Defect plausibly caused by material quality or formation issue | crack, deformation, inclusion |
| `Contamination` | Foreign material, stain, particle, color residue | contamination, color spot, dirt, particles |
| `MissingComponent` | Expected visual component is absent | missing wire, missing part, missing connector |
| `SurfaceWear` | Repeated abrasion or surface degradation | worn area, shallow scratches, dull surface |
| `ProcessMisalignment` | Fixture, cutting, molding, or positioning issue | off-center, deformed, bent, shifted region |
| `PackagingPressure` | Compression or pressure during packaging/transport | squeeze, crack, flattening |

## Annotation Unit

Annotate at the defect-type level first. Sample-level annotation can be added
later if images show multiple defect mechanisms.

Minimum annotation fields:

```csv
annotation_id,object,defect_type,location,morphology,root_cause_id,root_cause_name,evidence,confidence,review_status,source
```

Example:

```csv
mvtec_rca_001,metal_nut,scratch,surface,linear,MechanicalContact,Mechanical contact,"scratch is a linear surface defect consistent with contact damage",0.75,reviewed,manual_curation
```

## KG Edge Pattern

Each annotation should become source-constrained KG edges.

Core visual semantics:

```text
ScratchDefect --HAS_MORPHOLOGY--> LinearMorphology
ScratchDefect --OCCURS_ON--> SurfaceLocation
```

Plausible RCA:

```text
ScratchDefect --HAS_PLAUSIBLE_CAUSE--> MechanicalContact
MechanicalContact --PART_OF--> HandlingDamage
```

Every edge must keep:

```text
source = manual_curation | caption_mask_stats | dataset_label | paper | thesis
evidence = exact annotation rationale or source text
confidence = float in [0, 1]
weight = 1 - confidence
review_status = auto | reviewed | rejected
```

## Confidence Rules

Use conservative confidence values:

| Situation | Suggested confidence |
|---|---:|
| Direct dataset defect label to defect node | 0.85-0.95 |
| Mask/caption strongly supports morphology or location | 0.75-0.90 |
| Manual plausible RCA mapping reviewed by project author | 0.65-0.80 |
| Weak industrial heuristic without source | 0.40-0.60 |
| LLM-suggested mapping before review | 0.30-0.55 |

Do not mark an RCA edge as `reviewed` unless a human has explicitly accepted
the rationale.

## Suggested First Batch

Start with 15-30 annotations, enough for pipeline development and tests.

| Object | Defect | Suggested root causes |
|---|---|---|
| `metal_nut` | `scratch` | `MechanicalContact`, `HandlingDamage`, `SurfaceWear` |
| `metal_nut` | `color` | `Contamination`, `MaterialDefect` |
| `cable` | `cut` | `MechanicalContact`, `AssemblyError` |
| `cable` | `missing_wire` | `MissingComponent`, `AssemblyError` |
| `cable` | `bent_wire` | `AssemblyError`, `ProcessMisalignment` |
| `screw` | `scratch_neck` | `MechanicalContact`, `SurfaceWear` |
| `bottle` | `contamination` | `Contamination` |
| `bottle` | `broken_large` | `HandlingDamage`, `PackagingPressure` |
| `capsule` | `crack` | `MaterialDefect`, `PackagingPressure` |
| `capsule` | `squeeze` | `PackagingPressure`, `HandlingDamage` |
| `pill` | `crack` | `MaterialDefect`, `PackagingPressure` |
| `pill` | `contamination` | `Contamination` |

These are development hypotheses. Before formal experiments, review the exact
MVTec/DS-MVTec defect folders and sample images, then update the evidence text.

## Evaluation Protocol For Development

Clean RCA:

- Input clean evidence generated from defect label, caption, and mask.
- Run entity linking and path ranking.
- Count a hit if top-k path reaches any reference root cause for that defect.

Noisy RCA:

- Corrupt `anomaly_type`, `location`, or `morphology`.
- Run consistency checking and correction.
- Count recovery when corrected evidence restores a path to the reference root
  cause.

Case study:

- Show image or mask region.
- Show structured evidence.
- Show linked entities.
- Show inconsistent fields.
- Show correction candidates.
- Show top-k RCA paths with source edges.

## Source Notes

- MVTec official documentation describes the dataset folder structure and
  pixel-precise anomaly masks:
  <https://www.mvtec.com/company/research/datasets/mvtec-ad/downloads?cHash=a79aa4ef833d7bfed981e2fba6342c8f&gad_source=1>
- Defect Spectrum provides richer semantics, captions, and mask-oriented
  DS-MVTec files:
  <https://huggingface.co/datasets/DefectSpectrum/Defect_Spectrum>
- Defect Spectrum paper:
  <https://arxiv.org/abs/2310.17316>
