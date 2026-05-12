# Wafer Sources

Record source excerpts or private-source summaries used for wafer KG construction here.
Do not commit confidential raw data.

## Coverage-First Candidate KG Sources

- `wm811k_public_pattern_classes`: WM811K public defect-pattern vocabulary used
  by the local producer/model path: Center, Donut, Edge-Loc, Edge-Ring, Loc,
  Random, Scratch, and Near-full. These classes are defect-pattern evidence, not
  process root-cause labels.
- `wm811k_pattern_semantics`: deterministic class-to-location/morphology rules
  aligned with the wafer-map descriptor helper in `src/kgtracevis/mask/`.
- `wm811k_low_confidence_investigation_rule`: conservative candidate mechanism
  mappings used to generate plausible investigation paths. These default to
  `review_status=auto` and low/medium confidence unless separately reviewed.
