# TEP RBC Reference Notes

Reviewed prior project files:

- `/Users/hhm/code/TEP_KG/docs/sequence-data-structure.md`
- `/Users/hhm/code/TEP_KG/src/tep_kg/rbc.py`
- `/Users/hhm/code/TEP_KG/scripts/build_rbc.py`

Relevant source shape:

- TEP CSV columns are `faultNumber`, `simulationRun`, `sample`,
  `xmeas_1..xmeas_41`, and `xmv_1..xmv_11`.
- The prior flow builds a fault-free statistical profile, then streams faulty
  windows grouped by `(faultNumber, simulationRun)`.
- Residual-based contribution (RBC) computes normalized reconstruction residual
  mass per channel and surfaces top channels/variables for RCA.

KGTraceVis implementation decision:

- Re-implement the same producer concept natively under
  `src/kgtracevis/producers/`.
- Use NumPy eigendecomposition for the profile/reconstruction step.
- Emit adapter-ready producer records directly, including stable case IDs and
  TEP fault/run metadata required by `TepScenarioSelector`.
- Keep source-to-KG/RCA provider behavior separate; this task only creates the
  raw-data-to-record producer entrypoint.
