# Research: wafer factory document audit

- Query: Inspect current wafer KG construction/docs and audit `/Users/hhm/Downloads/文档类` documents for usefulness as source provenance for wafer KG hardening.
- Scope: internal
- Date: 2026-05-13

## Findings

### Repository Context

#### Files Found

- `data/kg/wafer_nodes.csv` - tracked wafer KG node file; currently only contains the required CSV header.
- `data/kg/wafer_edges.csv` - tracked wafer KG edge file; currently only contains the required CSV header.
- `docs/sources/wafer_sources.md` - current wafer source note file; lists WM811K public pattern vocabulary, deterministic pattern semantics, and low-confidence investigation rules.
- `data/kg/source_registry.csv` - central source registry; already contains `wm811k_public_pattern_classes`, `wm811k_pattern_semantics`, and `wm811k_low_confidence_investigation_rule`.
- `src/kgtracevis/kg_construction/case_kg_hardening.py` - coverage-first candidate KG generator for MVTec and WM811K/wafer artifacts.
- `src/kgtracevis/mask/wafer_map_features.py` - deterministic wafer-map descriptor helper used to derive location/morphology/severity from pattern and spatial descriptors.
- `src/kgtracevis/adapters/wm811k_adapter.py` - WM811K adapter that emits observed wafer evidence while keeping `produces_root_cause=False`.
- `docs/kg_hardening_pipeline.md` - documents the coverage-first KG hardening pipeline and claim boundaries.
- `docs/ontology_schema.md` - documents node and edge CSV contracts.
- `data/examples/records/wm811k_records.jsonl` - small WM811K producer-record fixture.
- `data/examples/wafer_example.json` - manual/demo wafer evidence example.

#### Code Patterns

- Tracked wafer CSVs are empty except headers, so current stable wafer KG does not yet contain reviewed wafer source rows (`data/kg/wafer_nodes.csv:1`, `data/kg/wafer_edges.csv:1`).
- Current wafer source docs already separate public pattern classes, deterministic pattern semantics, and low-confidence investigation rules (`docs/sources/wafer_sources.md:8`, `docs/sources/wafer_sources.md:12`, `docs/sources/wafer_sources.md:14`).
- Source registry has wafer entries for WM811K pattern coverage, descriptor semantics, and low-confidence investigation rules (`data/kg/source_registry.csv:6`, `data/kg/source_registry.csv:7`, `data/kg/source_registry.csv:8`).
- Candidate KG generation declares claim boundary text: candidate/plausible explanation only, not verified RCA (`src/kgtracevis/kg_construction/case_kg_hardening.py:30`).
- Candidate validation blocks unreviewed `CAUSED_BY` edges and forbidden verified-RCA wording (`src/kgtracevis/kg_construction/case_kg_hardening.py:813`, `src/kgtracevis/kg_construction/case_kg_hardening.py:821`).
- WM811K pattern specs map classes to candidate locations, morphologies, and mechanism IDs (`src/kgtracevis/kg_construction/case_kg_hardening.py:379`).
- Wafer candidate rows currently create `HAS_ANOMALY`, `HAS_MORPHOLOGY`, `OCCURS_ON`, and low-confidence `HAS_PLAUSIBLE_CAUSE` edges (`src/kgtracevis/kg_construction/case_kg_hardening.py:1201`, `src/kgtracevis/kg_construction/case_kg_hardening.py:1212`, `src/kgtracevis/kg_construction/case_kg_hardening.py:1223`, `src/kgtracevis/kg_construction/case_kg_hardening.py:1237`).
- Wafer descriptor rules derive `nearfull -> wafer_surface`, `center -> center`, edge classes -> `edge`, `loc -> local`, and pattern-to-morphology rules such as `scratch -> linear`, `edge_ring/donut -> ring` (`src/kgtracevis/mask/wafer_map_features.py:68`, `src/kgtracevis/mask/wafer_map_features.py:100`).
- WM811K adapter explicitly emits dataset `wafer`, adapter `wm811k`, observed pattern/location/morphology evidence, and does not emit root-cause output (`src/kgtracevis/adapters/wm811k_adapter.py:75`, `src/kgtracevis/adapters/wm811k_adapter.py:108`, `src/kgtracevis/adapters/wm811k_adapter.py:131`).
- KG hardening docs state WM811K model outputs are defect-pattern evidence, not process RCA labels, and candidate mechanism paths remain investigation aids (`docs/kg_hardening_pipeline.md:8`, `docs/kg_hardening_pipeline.md:79`).
- Ontology docs require every non-example edge to be source-constrained and reviewable (`docs/ontology_schema.md:15`).

#### Related Specs

- `.trellis/spec/backend/database-guidelines.md` - CSV contracts, source-constrained KG construction rules, and candidate status as edge metadata.
- `.trellis/spec/backend/adapter-guidelines.md` - WM811K adapter evidence-boundary rules and `produces_root_cause=False`.
- `.trellis/spec/backend/wm811k-model-presets.md` - WM811K producer/model outputs are defect-pattern classification, not verified RCA.
- `.trellis/spec/backend/quality-guidelines.md` - every KG edge must include provenance, confidence, review status, and claim boundaries.

#### External References

- No web sources were used. This audit is based on local repository files and local documents under `/Users/hhm/Downloads/文档类`.
- Extraction tools used locally: macOS `textutil` for Word text checks, Python `pypdf` for extractable PDFs, direct ZIP/XML inspection for `.docx`/`.xlsx`, and encoding-aware local reads for `.txt`, `.log`, `.CSV`, and `.json`.

### Local Document Audit

#### Top-Level Documents

| Filename | Type | Readable / extractable | Concise content summary | Wafer/KG usefulness | Safe `source_id` suggestion | Short evidence snippets | Claim-boundary risks |
|---|---:|---|---|---|---|---|---|
| `1599#陪片 说明书-最终版.docx` | Word manual | Yes; text extracted | SFQ-810YXPX 8-inch wafer carrier/monitor-wafer cleaning machine manual. Covers RCA cleaning process, process tanks, chemicals, alarms, WPR, facility needs, maintenance. | Medium for equipment/process nodes and alarm/process-unit edges; low for defect/RCA; none for verified morphology/location. | `factory_manual_sfq810yxpx_2024` | `200 mm（8 英寸）...标准 RCA 清洗工艺`; `Wafer Process Robot`; `SPM RT+10~130 ℃`; `IPA & N2` | Official-style equipment manual supports equipment capability and process-unit vocabulary, not defect root causes. Do not infer wafer defect morphology/location from this manual. |
| `EN-05-D77-150 8寸WTS 设备通讯手册.pdf` | PDF communication manual | Yes; 12 pages extracted | 8-inch WTS STK communication interface. Covers HSMS/SECS-II, device IDs, cassette/mapping data, pusher/station/rule messages. | Medium for equipment communication nodes and log-event normalization; none for defect morphology/RCA. | `factory_wts_comm_en05d77150_2024` | `8 Inch WTS STK Communication Interface`; `HSMS&SECS-II`; `MappingData`; `ErrorID ErrorText` | Communication protocol source only. It can support event/log entity names but not physical causality or defect classes. |
| `EN-05-D77-151 8寸 WTS 设备手册.pdf` | PDF equipment manual | Yes; 46 pages extracted | 8-inch WTS equipment manual. Covers WTS transport/pusher/mapping modules, robot operation, system performance, alarm/error information. | Medium for process/equipment nodes and transfer/mapping failure events; low for breakage/fragment rate constraints; none for pattern morphology/RCA. | `factory_wts_manual_en05d77151_2024` | `Pusher...具有Mapping检测功能`; `Wafer 片朝向功能`; `Robot 位置出现偏差，取放片频繁失败`; `碎片率 ≤1/50000` | Supports WTS handling/mapping mechanics and reliability specs, not direct wafer-map defect morphology. Any handling-to-scratch cause edge would need low confidence and manual review. |
| `异常SOP.txt` | Text SOP / local knowledge summary | Yes; UTF-8 text | SOP-style wet-cleaning abnormality text. Contains explicit statements linking process issues, alarms, and defect labels such as `nearfull`, `边缘环`, `甜甜圈`, `中心圆`, `划痕`. | High for candidate source discovery; medium for defect-vocabulary alignment; low for KG causality until reviewed. Most valuable single source for wafer hardening, but not safe as verified RCA. | `factory_abnormal_sop_wet_cleaning_local` | `出片间隔过短...晶圆“near full”类型的缺陷`; `软件异常会导致划痕缺陷、nearfull缺陷、边缘环缺陷、甜甜圈缺陷、中心圆缺陷`; `供液不足会导致晶圆去胶不充分`; `浸泡去胶不充分导致边缘环缺陷` | This appears partly derived from triples or synthesized procedural knowledge (`基于三元组信息`). It supports low-confidence/manual-review candidate edges, not reviewed factory RCA. It names defect patterns but does not provide image morphology/location measurements. |
| `本1.pdf` | PDF manual | Barely; 576 pages but only minimal text extracted | Likely scanned/encoded duplicate of the Clean-1 Wet Bench manual split into `本1_*.docx`. | Low because text is not reliably extractable; use DOCX splits instead. | `scientech_clean_wet_bench_manual_pdf_k019040042` | No reliable short evidence text extracted. | Do not use as primary source unless OCR/visual review is performed. |
| `本1_1-200.docx` | Word manual part | Yes; text extracted | 200mm Clean-1 Wet Bench manual pages 1-200. Covers safety, equipment structure, process tanks, WPR/WPL/CTM, chemicals and operating screens. | Medium for equipment/process nodes and process-step vocabulary; low/none for defect/RCA. | `scientech_clean_wet_bench_manual_k019040042_part1` | `200 mm Clean Wet Bench`; `SPM`; `BOE`; `DHF`; `SC1`; `Megasonic`; `DIW`; `IPA` | Good source for wet-bench ontology vocabulary. It does not prove defect-pattern morphology or root cause. |
| `本1_201-400.docx` | Word manual part | Yes; text extracted | Clean-1 Wet Bench parameter/operation section. Covers tank parameters, spiking, wafer-count triggers, DIW resistance, process and alarm parameter settings. | Medium for recipe/parameter nodes and abnormal process-event vocabulary; low for RCA. | `scientech_clean_wet_bench_manual_k019040042_part2` | `After Wafer Count Function`; `DIW 水阻值异常`; `Chemical Life Time Reset`; `Megasonic` | Can support parameter nodes and alarm/event names. Causal links to defects still require separate review. |
| `本1_401-576.docx` | Word manual part | Yes; text extracted | Clean-1 Wet Bench maintenance/alarm section. Covers WPL/WPR maintenance, alarm codes, pump/sensor troubleshooting, acceptance checklist. | Medium for equipment-fault/log-event nodes; low for candidate RCA; none for morphology/location. | `scientech_clean_wet_bench_manual_k019040042_part3` | `Megasonic...运转异常`; `检修 Pump`; `Wafer Stand`; `Alarm Reset` | Troubleshooting actions support possible fault-event taxonomy, not defect causality unless cross-checked against SOP or cases. |
| `本2.docx` | Word appendix | Yes; text extracted | Clean Wet Bench appendices: system diagrams, electrical drawings, OEM parts, consumables/spares, component lists. | Medium for component/process-unit node names; low for alarm/entity aliases; none for defect morphology/RCA. | `scientech_clean_wet_bench_appendix_k019040042` | `Wafer counter`; `SPM浓度计`; `IPA浓度侦测器`; `Megasonic 70110`; `DIW MONITOR` | Parts lists are strong for component vocabulary but cannot support causal edges by themselves. |
| `本2.pdf` | PDF appendix | Barely; 784 pages but only minimal text extracted | Likely scanned/encoded duplicate of `本2.docx`. | Low; use DOCX instead. | `scientech_clean_wet_bench_appendix_pdf_k019040042` | No reliable short evidence text extracted. | Do not use as primary source unless OCR/visual review is performed. |
| `本3.docx` | Word manual | Yes; text extracted | 200mm SiN Remove Wet Bench manual. Covers safety, SiN-removal process units, WTM/WPR/WPL, tanks, H3PO4/DHF/SPM, DIW, megasonic, parameters and alarms. | Medium for process/equipment nodes; low for process-fault candidates; none for verified defect morphology/RCA. | `scientech_sin_remove_manual_k019040043` | `200 mm SiN Remove Wet Bench`; `Wafer Process Robot`; `After Wafer Count Function`; `DHF`; `H3PO4`; `Megasonic` | Process tool manual supports process context only. Do not generalize SiN-removal tool behavior into WM811K defect causes without review. |
| `本3.pdf` | PDF manual | Barely; 564 pages but only minimal text extracted | Likely scanned/encoded duplicate of `本3.docx`. | Low; use DOCX instead. | `scientech_sin_remove_manual_pdf_k019040043` | No reliable short evidence text extracted. | Do not use as primary source unless OCR/visual review is performed. |
| `本4.docx` | Word appendix | Yes; text extracted | SiN Remove Wet Bench appendices: system/electrical drawings, OEM parts, consumables, component lists. | Medium for component aliases and process-unit nodes; low for KG causality; none for morphology/location. | `scientech_sin_remove_appendix_k019040043` | `Wafer counter`; `SPM 浓度计`; `IPA浓度侦测器`; `Megasonic 70110`; `DIW MONITOR` | Use for vocabulary/source aliases only unless combined with abnormal SOP and reviewed incident cases. |
| `本4.pdf` | PDF appendix | Barely; 796 pages but only minimal text extracted | Likely scanned/encoded duplicate of `本4.docx`. | Low; use DOCX instead. | `scientech_sin_remove_appendix_pdf_k019040043` | No reliable short evidence text extracted. | Do not use as primary source unless OCR/visual review is performed. |
| `湿法设备零部件&电气元件&程序&HMI&上位软件命名规范 V2024-01.xlsx` | Excel naming standard | Yes; ZIP/XML text extracted | Naming standard with sheets `零部件` and `上位软件`. Contains component/program/HMI terms for wafer transfer, WPR, WPL, process tanks, recipes, interlocks, sensors, DIW/IPA/megasonic. | Medium-high for alias normalization and node naming; none for defect causality. | `wetbench_naming_standard_2024_01` | `晶圆工艺机械手`; `Wafer Process Robot`; `Wafer Process Lifter`; `Recipe Name`; `Process Tank`; `Interlock Sensor` | Excellent for aliases and stable display names. It should not create RCA edges. |

#### Operational File Collections

The two top-level directories contain many operational files. They are not narrative documents, but they are useful as provenance for recipe/log entities if curated.

| Collection | Type | Readable / extractable | Concise content summary | Wafer/KG usefulness | Safe `source_id` suggestion | Short evidence snippets | Claim-boundary risks |
|---|---:|---|---|---|---|---|---|
| `设备配方/RecipeFile/*.json` | 10 JSON recipe files | Yes; UTF-8 JSON | Recipe parameter sets with `ProcessNN`/`StepNN`, modes such as `FIXED`, `IPA`, `MEGA`, `DIW`, `DRY`, `RECYCLENMP`, `ACE`, and parameters such as `dDunkTemp`, `iDunkTime`, `dPumpPressure`, `dMainSpeed`, `iRunTime`. | High for recipe/parameter nodes and evidence observations; medium for process-condition constraints; none for causality unless paired with labeled incidents. | `wetbench_recipe_samples_local` | `iMode: FIXED`; `dDunkTemp: 70.0`; `iMode: MEGA`; `dPumpPressure: 1800.0`; `iMode: DRY` | Recipes are actual configuration evidence, not defect labels. Do not create `CAUSES`/`HAS_PLAUSIBLE_CAUSE` edges from recipe values alone. |
| `机台日志/RunStateLog/**/*.CSV` | 1055 GB18030-style CSV run-state files | Partly; encoded operational CSVs | Cassette/run-state records with timestamps, routes, station/movement information. Example first rows decode as cassette/run route and start time. | Medium for log-event/entity extraction, run context, and temporal evidence; low for KG source provenance until schema is parsed. | `wetbench_runstate_logs_local` | `2018/09/12/09:47:24`; `p1t1`; `1->25` | Needs schema reverse engineering before KG ingestion. No direct defect labels found in sampled records. |
| `机台日志/log/**/*.log` | 344 GB18030 log files | Yes; decoded with GB18030 | Operator, production, warning, and fault logs from 2020-2026. Keyword counts: `报警` 8551 hits, `失败` 1237, `停止` 1709, `漏液` 73, `IPA` 3560, `DIW` 398, only sparse `晶圆` hits. | Medium-high for alarm/event vocabulary and case evidence; low for defect/RCA unless matched to wafer labels. | `wetbench_operator_logs_local` | `水压故障报警`; `机械手报警复位失败`; `设备漏液,浸泡区`; `IPA罐高高液位报警`; `清除晶圆状态1` | Logs are observed events, not confirmed causes. They can support `log_event` nodes and evidence records, but not defect morphology/location without case alignment. |

### Factory-Collaboration Claim Boundary Assessment

- The only local document that explicitly links factory/process conditions to wafer defect classes is `异常SOP.txt`.
- `异常SOP.txt` can support candidate process/RCA edges for manual review, for example:
  - `CassetteIntervalTooShort -> NearfullDefect`
  - `SoftwareAbnormalExit -> WaferScratchDefect / NearfullDefect / EdgeRingDefect / DonutDefect / CenterDefect`
  - `FixedWaterNotEnabled`, `MegasonicWaterNotEnabled`, `IPAUnavailable`, `DIWUnavailable -> NearfullDefect`
  - `InsufficientResistStripping -> NearfullDefect / EdgeRingDefect / DonutDefect`
  - `WaferDrop` or `TransferAccelerationTooHigh -> WaferScratchDefect`
- However, those are process/RCA claims, not verified factory root-cause labels. The SOP wording appears generalized and possibly generated from prior triples, so candidate edges should default to low confidence (`0.35-0.55`), `review_status=auto`, and evidence text should retain candidate/manual-review wording.
- For wafer defect pattern morphology/location, the SOP only offers textual defect-name hints:
  - `边缘环` is compatible with `edge_ring`/ring-at-edge semantics.
  - `甜甜圈` is compatible with `donut`/ring semantics.
  - `中心圆` is compatible with `center`/center-cluster semantics.
  - `划痕` is compatible with `scratch`/linear semantics.
  - `near full`/`nearfull` is compatible with dense/full-surface evidence.
- Those hints can corroborate existing WM811K class aliases but should not replace deterministic WM811K pattern semantics from `src/kgtracevis/mask/wafer_map_features.py`.
- The equipment manuals, naming spreadsheet, recipes, and logs support process-unit, component, alarm, recipe, and event vocabulary. They do not independently support verified defect morphology/location or root cause.

### Concrete Recommendations

#### Source Registry / Docs Additions

Add source registry rows, after manual review, for:

- `factory_abnormal_sop_wet_cleaning_local` - type `private_factory_sop_summary`; path `docs/sources/wafer_sources.md`; used for low-confidence wafer process/RCA candidate edges; note: "Local/private SOP-style summary; candidate only; manual review required."
- `factory_manual_sfq810yxpx_2024` - type `private_equipment_manual`; used for wet-cleaning equipment/process-unit vocabulary and RCA-clean process context; no defect causality.
- `factory_wts_manual_en05d77151_2024` - type `private_equipment_manual`; used for WTS transfer/mapping/robot/event vocabulary; no defect causality.
- `factory_wts_comm_en05d77150_2024` - type `private_comm_manual`; used for HSMS/SECS-II and error/log-event normalization.
- `wetbench_naming_standard_2024_01` - type `private_naming_standard`; used for aliases and display names for equipment/component/HMI/recipe entities.
- `wetbench_recipe_samples_local` - type `private_recipe_samples`; used for recipe parameter evidence and process-step observations, not RCA.
- `wetbench_operator_logs_local` and `wetbench_runstate_logs_local` - type `private_equipment_logs`; used for log-event observations after parsing and case alignment.

For `docs/sources/wafer_sources.md`, add short private-source summaries only. Do not commit raw manuals, long excerpts, full logs, or confidential tables.

#### KG Nodes Worth Adding

Candidate `wafer`/`shared` nodes supported by local documents:

- Process units/components: `WetBench`, `RcaCleanProcess`, `WaferTransferModule`, `WaferProcessRobot`, `WaferProcessLifter`, `ProcessTank`, `DryerTank`, `PusherModule`, `MappingModule`, `InterlockSensor`, `DIWMonitor`, `MegasonicUnit`, `IPABufferTank`, `ChemicalDispenseUnit`.
- Recipe/process parameters: `DunkTemperature`, `DunkTime`, `DunkInWaferTime`, `PumpPressure`, `RunTime`, `ArmSpeed`, `MainSpeed`, `SwayScope`, `RecipeModeFixed`, `RecipeModeIPA`, `RecipeModeMEGA`, `RecipeModeDIW`, `RecipeModeDRY`.
- Fault/log events: `WaterPressureAlarm`, `WaterResistivityAlarm`, `IPATankHighHighLevelAlarm`, `LeakAlarm`, `RobotResetFailure`, `SoftwareAbnormalExit`, `DoorNotClosed`, `SupplyFlowAlarm`, `CDAAlarm`, `WaferDrop`, `TransferPositionDeviation`.
- Defect aliases to existing/desired pattern nodes: `NearfullDefect` aliases `near full|nearfull`; `EdgeRingDefect` alias `边缘环`; `DonutDefect` alias `甜甜圈`; `CenterDefect` alias `中心圆`; `WaferScratchDefect` alias `划痕缺陷`.

#### KG Edges Worth Adding

Use conservative confidence and avoid `CAUSED_BY` unless reviewed. Suggested relations:

- High/medium confidence vocabulary/structure edges:
  - `WetBench HAS_PROCESS RcaCleanProcess` from `factory_manual_sfq810yxpx_2024`, confidence around `0.8`.
  - `WetBench HAS_COMPONENT WaferProcessRobot`, `WetBench HAS_COMPONENT ProcessTank`, `WetBench HAS_COMPONENT MegasonicUnit`, confidence around `0.75-0.85`.
  - `RecipeModeMEGA HAS_PARAMETER RunTime`, `RecipeModeFIXED HAS_PARAMETER DunkTemperature`, confidence around `0.75`, if the ontology accepts parameter relations.
  - `WaferProcessRobot HAS_ALIAS WPR` is better represented in node aliases, not as an edge.
- Low-confidence process/RCA candidate edges from `异常SOP.txt`:
  - `NearfullDefect HAS_PLAUSIBLE_CAUSE InsufficientRinseOrCleanFlow`, confidence `0.45-0.55`, evidence: short SOP snippet about unopened fixed/megasonic/IPA/DIW causing nearfull.
  - `NearfullDefect HAS_PLAUSIBLE_CAUSE InsufficientResistStripping`, confidence `0.45-0.55`.
  - `EdgeRingDefect HAS_PLAUSIBLE_CAUSE InsufficientResistStripping`, confidence `0.4-0.5`.
  - `DonutDefect HAS_PLAUSIBLE_CAUSE InsufficientResistStripping`, confidence `0.4-0.5`.
  - `WaferScratchDefect HAS_PLAUSIBLE_CAUSE TransferHandlingIssue`, confidence `0.45-0.55`.
  - `WaferScratchDefect HAS_PLAUSIBLE_CAUSE SpindleDischargeIssue`, confidence `0.4-0.5`.
  - `NearfullDefect HAS_PLAUSIBLE_CAUSE CassetteIntervalTooShort`, confidence `0.4-0.5`.
  - `WaferDefectPattern HAS_PLAUSIBLE_CAUSE SoftwareAbnormalExit`, confidence `0.35-0.45`, or split into individual pattern edges only if reviewers accept broad SOP wording.
- Alias/semantic corroboration edges, if needed:
  - Keep existing deterministic `HAS_MORPHOLOGY` and `OCCURS_ON` edges from WM811K pattern semantics as the primary morphology/location source.
  - Use SOP snippets only to add aliases (`边缘环`, `甜甜圈`, `中心圆`, `划痕缺陷`) or low-confidence corroboration notes, not primary morphology evidence.

#### Integration Guidance

- Treat local factory manuals as private source summaries. Add only short summaries and short snippets into `docs/sources/wafer_sources.md`.
- Keep process/RCA claims separate from WM811K observed defect-pattern evidence. The WM811K adapter and producer must continue to emit pattern evidence only.
- Any new wafer candidate mechanism edge from factory-collaboration material should include:
  - `source=factory_abnormal_sop_wet_cleaning_local`
  - short evidence snippet, not long copied text
  - `confidence <= 0.55` unless a human reviewer promotes it
  - `review_status=auto`
  - evidence wording such as "SOP-style local summary suggests..." or "candidate/manual-review edge".
- Do not add `CAUSED_BY` edges from these documents unless a reviewed factory incident/case label is supplied.
- Use logs and recipes later as evidence records or case alignment sources, not as KG causal truth.

## Caveats / Not Found

- No active Trellis task was set by the runtime, so the user-specified task directory was used explicitly.
- The audit did not modify code or tracked KG/docs files. It only writes this research file.
- Several PDFs (`本1.pdf`, `本2.pdf`, `本3.pdf`, `本4.pdf`) yielded almost no reliable text despite hundreds of pages; corresponding DOCX files are extractable and should be preferred unless OCR/manual page review is required.
- `异常SOP.txt` is the only audited document with explicit defect-causality statements, but it also contains language suggesting it may have been generated from triples or prior summaries. Its RCA claims need low confidence and manual review.
- No local document was found that independently validates WM811K wafer-map morphology/location from image labels. Existing deterministic WM811K pattern semantics remain the safest morphology/location source.
- Machine logs and run-state CSVs were audited as collections due volume (`1399` files total), with representative decoding and keyword checks. They require schema parsing and case alignment before they can support KG rows beyond log-event vocabulary.
