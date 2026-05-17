# Wafer User Study Baseline — Nearfull Case

- `case_id`: `wafer_user_study_nearfull_001`
- `dataset`: `wafer`
- `scope`: manual RCA baseline for user-study comparison only
- `claim boundary`: candidate/plausible explanation only; not a verified root-cause label

## Observed Evidence

- Wafer anomaly pattern: `nearfull`
- Location: `wafer_surface`
- Morphology: `dense_particles`
- Supporting observation: `example_alarm`
- Fixture note: this baseline is meant to be compared against RootLens-assisted RCA on the same wafer case.

## Baseline Candidate Ranking

| Rank | Candidate root cause | Basis |
| --- | --- | --- |
| 1 | `GlueRemovalInsufficient` | Existing reviewed wafer seed edge in `data/kg/edges.csv` links `NearfullDefect -> GlueRemovalInsufficient` with confidence `0.78`. |
| 2 | `WetCleanResidue` | Existing wafer scenario edge in `data/kg/wafer_edges.csv` links `NearfullDefect -> WetCleanResidue` with confidence `0.52`. |
| 3 | `ParticleContamination` | Existing wafer scenario edge in `data/kg/wafer_edges.csv` links `NearfullDefect -> ParticleContamination` with confidence `0.60`. |
| 4 | `RinseFlowInsufficient` | Existing wafer scenario edge in `data/kg/wafer_edges.csv` links `NearfullDefect -> RinseFlowInsufficient` with confidence `0.49`. |
| 5 | `WaterQualityExcursion` | Existing wafer scenario edge in `data/kg/wafer_edges.csv` links `NearfullDefect -> WaterQualityExcursion` with confidence `0.46`. |

## Suggested Baseline Procedure for Study Participants

1. Read the observed wafer anomaly fields above.
2. Review the ranked candidate causes without using RootLens.
3. Record your manual RCA choice and confidence.
4. Then use RootLens on the same case and compare:
   - speed
   - confidence
   - explanation quality
   - path plausibility

## Notes

- This baseline intentionally stays small and human-readable.
- It does **not** imply any verified process ground truth.
- It is aligned to the current local wafer seed KG and the existing plausible reference layer.
