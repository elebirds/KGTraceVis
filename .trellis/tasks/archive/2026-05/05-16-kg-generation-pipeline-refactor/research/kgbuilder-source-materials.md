# Research: KGBuilder source materials

- Query: Research the source/material inputs KGBuilder uses to generate KG, and how they overlap with KGTraceVis existing source docs/registries for a clean `source_kg_compiler` bypass.
- Scope: mixed
- Date: 2026-05-16

## Findings

### Task and spec context

The active Trellis runtime command reported no current task, but the user supplied the explicit task/output path: `.trellis/tasks/05-16-kg-generation-pipeline-refactor/research/kgbuilder-source-materials.md`.

Related PRD: `.trellis/tasks/05-16-kg-generation-pipeline-refactor/prd.md`

- The PRD names `source_kg_compiler` as the clean bypass and says the first implementation should generate `source_units.jsonl`, `knowledge_cards.jsonl`, `entities.jsonl`, `edges.jsonl`, KGTraceVis-compatible `nodes.csv` / `edges.csv`, `qa_report.json`, and `validation_report.json`.
- The PRD explicitly says not to use existing `DraftKG` as the primary compiler contract, because it would inherit current alignment/projection complexity too early.
- The PRD calls out strict generated-only validation as required to avoid default TEP/wafer/MVTec seed contamination.

Related specs:

- `.trellis/spec/backend/database-guidelines.md:16` defines the KGTraceVis node CSV contract: `id,name,label,scenario,aliases,description`.
- `.trellis/spec/backend/database-guidelines.md:31` defines the KGTraceVis edge CSV contract: `head,relation,tail,scenario,source,evidence,confidence,weight,review_status,feedback_count,accepted_count,rejected_count`.
- `.trellis/spec/backend/database-guidelines.md:49` warns that runtime should scope dataset-specific queries to selected dataset plus `shared`.
- `.trellis/spec/backend/database-guidelines.md:60` says `KnowledgeGraph.from_default_paths()` is mainly for seed/import validation and backward-compatible scripts, not clean single-overlay experiments.
- `.trellis/spec/backend/database-guidelines.md:217` requires source-constrained KG construction helpers to preserve source IDs, evidence text, confidence, weight, and reviewed-edge protection.
- `.trellis/spec/backend/workflow-architecture.md:96` says analysis workflows should not depend directly on KG construction internals.
- `.trellis/spec/backend/workflow-architecture.md:111` says construction pipelines own source loading, candidate extraction, review metadata, and KG version/export lifecycle.

### Files found

KGBuilder source/material pipeline:

- `/Users/hhm/code/KGBuilder/main.py` - six-step KGBuilder orchestration: load materials, chunk, extract cards, extract entities, build edges, export KG/QA/profiles/TEP view.
- `/Users/hhm/code/KGBuilder/config.py` - default materials/output dirs and chunk/model config.
- `/Users/hhm/code/KGBuilder/material_loader.py` - direct material loader and source registry writer.
- `/Users/hhm/code/KGBuilder/chunker.py` - character chunking layer used after material concatenation.
- `/Users/hhm/code/KGBuilder/knowledge_card_extractor.py` - card extraction from chunks, including deterministic explicit-relation cards.
- `/Users/hhm/code/KGBuilder/entity_extractor.py` - canonical entity extraction from cards.
- `/Users/hhm/code/KGBuilder/edge_builder.py` - edge extraction and deterministic explicit-relation edge compiler.
- `/Users/hhm/code/KGBuilder/exporter.py` - KGBuilder JSON/CSV exports plus KGTraceVis-compatible `kgtracevis_nodes.csv` / `kgtracevis_edges.csv`.
- `/Users/hhm/code/KGBuilder/domain_profile_extractor.py` - scenario profile extraction/compilation from generated KG.
- `/Users/hhm/code/KGBuilder/tep_root_kgd_projector.py` - TEP Root-KGD runtime-view projection and overlay export.
- `/Users/hhm/code/KGBuilder/materials/mvtec_source_notes.md` - source-backed MVTec notes used as a top-level ingested material.
- `/Users/hhm/code/KGBuilder/materials/wafer_source_notes.md` - source-backed wafer notes used as a top-level ingested material.
- `/Users/hhm/code/KGBuilder/materials/tep_source_notes.md` - source-backed TEP notes used as a top-level ingested material.
- `/Users/hhm/code/KGBuilder/materials/source_docs/mvtec_ad.pdf` - raw traceability document, not directly ingested unless moved to top-level `materials/`.
- `/Users/hhm/code/KGBuilder/materials/source_docs/wafer_yield_prediction_spatial_variables.pdf` - raw traceability document, not directly ingested unless moved to top-level `materials/`.
- `/Users/hhm/code/KGBuilder/materials/source_docs/tennessee_eastman_dataset_readme.html` - raw traceability snapshot, not directly ingested unless moved to top-level `materials/`.
- `/Users/hhm/code/KGBuilder/profiles/tep_root_kgd_seed.json` - versioned TEP Root-KGD seed profiles, variable mapping, and runtime ID mappings.
- `/Users/hhm/code/KGBuilder/outputs/source_registry.csv` - actual KGBuilder ingested material inventory for the current output run.
- `/Users/hhm/code/KGBuilder/outputs/kgtracevis_nodes.csv` and `/Users/hhm/code/KGBuilder/outputs/kgtracevis_edges.csv` - KGTraceVis-compatible CSV view.
- `/Users/hhm/code/KGBuilder/outputs/tep_root_kgd_view/` - generated TEP runtime view assets.

KGTraceVis source/material and registry overlaps:

- `data/kg/source_registry.csv` - existing KGTraceVis source registry covering seed examples, MVTec docs, wafer docs/private summaries, TEP artifacts, and runtime projection references.
- `docs/sources/mvtec_sources.md` - MVTec source-purpose notes and claim boundaries.
- `docs/sources/wafer_sources.md` - wafer source-purpose notes, private-source audit, and claim boundaries.
- `docs/sources/tep_sources.md` - TEP source-purpose notes and local sibling-project artifact boundaries.
- `docs/sources/mvtec_source_bundle/README.md` and `manifest.json` - MVTec provenance bundle inventory.
- `src/kgtracevis/workflows/mvtec_llm_source_pack.py` - KGTraceVis MVTec raw/near-raw source pack builder.
- `src/kgtracevis/workflows/wafer_llm_source_pack.py` - KGTraceVis wafer raw/near-raw source pack builder.
- `src/kgtracevis/service/kg_materials.py` - KGTraceVis material-library DTOs, registration, extraction, and selected-material build prep.
- `src/kgtracevis/workflows/material_kg_construction.py` - reusable material-library-to-source-KG orchestration.
- `src/kgtracevis/kg_construction/source_loader.py` - legacy registry loader for `data/kg/source_registry.csv`.
- `src/kgtracevis/kg_construction/sources.py` - newer Source Library record contract.
- `src/kgtracevis/kg/graph.py` - default KG seed path definitions that create strict-generated-only contamination risk.

### KGBuilder material input shape

KGBuilder is materially simpler than the current KGTraceVis material pipeline:

- The CLI accepts `--materials`, `--outputs`, `--scenario`, and optional `--tep-calibration-records` in `/Users/hhm/code/KGBuilder/main.py:22`.
- The main pipeline is linear: `load_materials`, `chunk_materials`, `extract_knowledge_cards`, `extract_entities`, `build_edges`, then export QA/profiles/TEP view in `/Users/hhm/code/KGBuilder/main.py:52`.
- Defaults are a single top-level `materials/` directory and `outputs/` directory in `/Users/hhm/code/KGBuilder/config.py:12`.
- Supported directly ingested extensions are `.txt`, `.md`, `.csv`, `.json`, and `.pdf` in `/Users/hhm/code/KGBuilder/material_loader.py:12`.
- Only files directly under `materials/` are loaded by `load_materials`; the README states `materials/source_docs/` is traceability only unless those files are moved to top-level materials (`/Users/hhm/code/KGBuilder/README.md:69`).
- The current KGBuilder output registry has only three ingested source rows: `mvtec_source_notes.md`, `tep_source_notes.md`, and `wafer_source_notes.md` (`/Users/hhm/code/KGBuilder/outputs/source_registry.csv:1`).

The directly reusable compiler boundary is therefore:

1. Top-level source units/material records with stable IDs, paths, hashes, scenario, and purpose.
2. Text chunks with source unit IDs.
3. Knowledge cards with `source_chunk_id`, `source_material_ids`, `evidence_text`, scenario, claim, entities, and relation hints.
4. Canonical entities with stable IDs, aliases, scenario, and source card references.
5. Edges with stable IDs, endpoints, relation, scenario, evidence, source card references, confidence, weight, review status, and feedback counters.
6. KGTraceVis-compatible CSV projection.

This directly matches the task PRD's proposed compiler artifact chain.

### KGBuilder code patterns worth reusing

Directly reusable:

- Linear orchestration. `/Users/hhm/code/KGBuilder/main.py:52` through `/Users/hhm/code/KGBuilder/main.py:101` is the clearest reference for the new `source_kg_compiler`: each stage reads/writes explicit artifacts and no hidden runtime graph load occurs.
- Material inventory. `/Users/hhm/code/KGBuilder/material_loader.py:29` writes `combined_materials.txt` and `source_registry.csv`, with path, SHA-256, size, intended use, and notes.
- Card contract. `/Users/hhm/code/KGBuilder/knowledge_card_extractor.py:48` requires card ID, scenario, claim, entities, relation hints, source chunk ID, source material IDs, and evidence text.
- Explicit-relation fast path. `/Users/hhm/code/KGBuilder/knowledge_card_extractor.py:99` converts source lines such as `CableObject HAS_ANOMALY BentCableDefect` into cards before LLM extraction. `/Users/hhm/code/KGBuilder/edge_builder.py:171` converts such cards into deterministic edges.
- Scenario batching. `/Users/hhm/code/KGBuilder/entity_extractor.py:107` and `/Users/hhm/code/KGBuilder/edge_builder.py:214` batch by scenario to reduce over-merging across MVTec/wafer/TEP.
- Edge constraints and RCA metadata. `/Users/hhm/code/KGBuilder/edge_builder.py:13` defines the relation whitelist; `/Users/hhm/code/KGBuilder/edge_builder.py:31` maps relation families; `/Users/hhm/code/KGBuilder/edge_builder.py:49` defines propagation-enabled relation types; `/Users/hhm/code/KGBuilder/edge_builder.py:60` applies target-type constraints.
- KGTraceVis CSV projection. `/Users/hhm/code/KGBuilder/exporter.py:55` writes `kgtracevis_nodes.csv`, `kgtracevis_edges.csv`, `published_nodes.csv`, and `published_edges.csv` using KGTraceVis's runtime/import columns.
- Domain profiles as separate downstream artifacts. `/Users/hhm/code/KGBuilder/domain_profile_extractor.py:156` exports `domain_profiles.json` and a profile report after KG generation, so profiles do not complicate the core source-to-edge loop.
- TEP projection as explicit runtime view. `/Users/hhm/code/KGBuilder/tep_root_kgd_projector.py:107` exports the Root-KGD-compatible view under `outputs/tep_root_kgd_view/` and overlay CSVs, instead of mixing the projection into canonical KG generation.

Reusable with modification:

- KGBuilder uses `.json` arrays and generic CSV names. The PRD asks for JSONL artifacts (`source_units.jsonl`, `knowledge_cards.jsonl`, `entities.jsonl`, `edges.jsonl`) and KGTraceVis-compatible `nodes.csv` / `edges.csv`; reuse concepts, not filenames.
- KGBuilder edge dedupe resets confidence to `0.7` and `review_status=auto` in `/Users/hhm/code/KGBuilder/edge_builder.py:279`; the compiler should preserve source-type confidence where KGTraceVis can compute it.
- KGBuilder's default LLM/model config is DeepSeek/OpenAI-compatible (`/Users/hhm/code/KGBuilder/config.py:17`); KGTraceVis should keep provider/model metadata explicit and not hard-code a provider into the compiler contract.

Do not directly reuse:

- Demo material fallback in `/Users/hhm/code/KGBuilder/material_loader.py:15`; KGTraceVis compiler should fail on empty source inputs rather than generating demo facts.
- Hidden dependence on `~/code/KGTraceVis/.env.local` in `/Users/hhm/code/KGBuilder/config.py:15`; compiler should use explicit config/environment behavior.
- Direct use of KGTraceVis checked-in TEP Root-KGD reference assets inside the core compiler. `/Users/hhm/code/KGBuilder/tep_root_kgd_projector.py:15` defaults to `~/code/KGTraceVis/data/kg/tep_root_kgd`; for the bypass, this belongs only in an optional runtime-view projection/validation step.

### Source purpose by scenario

#### MVTec

KGBuilder direct material:

- `/Users/hhm/code/KGBuilder/materials/mvtec_source_notes.md`
- Purpose: MVTec AD dataset context, object categories, defect types, visual evidence requirements, and explicit reusable relation lines.
- It cites the official MVTec AD page, a locally downloaded MVTec AD paper PDF, and PaDiM dataset-class documentation (`/Users/hhm/code/KGBuilder/materials/mvtec_source_notes.md:5`).
- It states grounded dataset facts such as 15 object/texture categories, split structure, and example defect types (`/Users/hhm/code/KGBuilder/materials/mvtec_source_notes.md:10`).
- It then adds RCA-KG construction notes and reusable relation lines, including plausible causes and required evidence (`/Users/hhm/code/KGBuilder/materials/mvtec_source_notes.md:18`, `/Users/hhm/code/KGBuilder/materials/mvtec_source_notes.md:23`, `/Users/hhm/code/KGBuilder/materials/mvtec_source_notes.md:42`, `/Users/hhm/code/KGBuilder/materials/mvtec_source_notes.md:62`).

KGTraceVis overlap:

- `docs/sources/mvtec_sources.md` records `mvtec_ad_official_page`, `mvtec_ad_paper_pdf`, PatchCore material, calibrated source labels, mask geometry, plausible visual mechanisms, and object-specific visual rules (`docs/sources/mvtec_sources.md:24`).
- `data/kg/source_registry.csv` includes `mvtec_ad_official_page`, `mvtec_ad_paper_pdf`, `patchcore_arxiv_abs`, `patchcore_arxiv_pdf`, `mvtec_object_specific_visual_rule`, and other MVTec source IDs (`data/kg/source_registry.csv:17`).
- `docs/sources/mvtec_source_bundle/manifest.json` has downloaded local HTML snapshots for the official page and PatchCore abstract, plus optional raw PDFs (`docs/sources/mvtec_source_bundle/manifest.json:6`).
- `src/kgtracevis/workflows/mvtec_llm_source_pack.py` already builds a raw/near-raw source pack with `mvtec_ad_official_page`, `ds_mvtec_dataset_card`, `mvtec_ad_paper_pdf`, visual-defect survey, injection-molding references, source bundle README, and optional PatchCore abstract (`src/kgtracevis/workflows/mvtec_llm_source_pack.py:143`).

Merge recommendation:

- Merge KGBuilder's `mvtec_source_notes.md` as an intermediate "source note" source unit only if it is marked as derived/curated and each explicit causal line remains `review_status=auto`.
- Prefer KGTraceVis `mvtec_ad_official_page`, `mvtec_ad_paper_pdf`, and DS-MVTec card/source-bundle materials as primary source units.
- Reuse KGBuilder's explicit relation line format as a seed-card mechanism for reviewed/curated notes, but keep source IDs linked back to KGTraceVis registry/material IDs.
- Do not promote MVTec plausible-cause edges as verified root causes. KGTraceVis already states MVTec paths are curated plausible explanations, not verified factory root causes (`docs/kg_hardening_pipeline.md:8`), and the material docs repeat this warning (`docs/kg_construction.md:454`).

#### Wafer / WM811K

KGBuilder direct material:

- `/Users/hhm/code/KGBuilder/materials/wafer_source_notes.md`
- Purpose: public wafer map/WM811K pattern classes, spatial morphology/location descriptors, plausible process hypotheses, and evidence requirements.
- It cites public wafer-map literature and a local PDF `materials/source_docs/wafer_yield_prediction_spatial_variables.pdf` (`/Users/hhm/code/KGBuilder/materials/wafer_source_notes.md:5`).
- It states WM811K classes and wafer-map pattern utility as source-grounded facts (`/Users/hhm/code/KGBuilder/materials/wafer_source_notes.md:10`).
- It includes explicit pattern, morphology/location, plausible-cause, and evidence-requirement relations (`/Users/hhm/code/KGBuilder/materials/wafer_source_notes.md:23`, `/Users/hhm/code/KGBuilder/materials/wafer_source_notes.md:42`, `/Users/hhm/code/KGBuilder/materials/wafer_source_notes.md:60`).

KGTraceVis overlap:

- `docs/sources/wafer_sources.md` records WM811K public classes, deterministic pattern semantics, low-confidence investigation rules, a wafer thesis/reference note, and private wet-clean/equipment summaries (`docs/sources/wafer_sources.md:6`).
- `data/kg/source_registry.csv` includes `wm811k_public_pattern_classes`, `wm811k_pattern_semantics`, `wm811k_low_confidence_investigation_rule`, private wafer summaries, and `wafer_thesis` (`data/kg/source_registry.csv:9`).
- `src/kgtracevis/workflows/wafer_llm_source_pack.py` defines a broader open-source material pack, including `wafer_defect_frontiers_2023`, `wafer_spatial_patterns_ntut_2006`, `wafer_root_cause_pattern_jstage`, `wafer_simple_feature_extraction_arxiv_2023`, Stanford spatial signature PDF, spatial filtering PDF, process references, and optional `wm811k_example_records` (`src/kgtracevis/workflows/wafer_llm_source_pack.py:125`).
- KGTraceVis docs state wafer/WM811K uses the same material pipeline and that the high-value default pair is an open wafer-defect source plus WM811K adapter evidence records (`docs/kg_construction.md:432`).

Merge recommendation:

- Reuse KGBuilder's wafer note as a curated source-note/card seed, but pair it with KGTraceVis source pack materials for provenance.
- Reuse KGTraceVis `wm811k_example_records` / adapter records as direct source units for observed pattern, zone, and morphology fields; they should generate explicit evidence descriptors, not causal facts.
- Merge KGTraceVis private wafer summaries only as source units with strict provenance and low-confidence candidate status. `docs/sources/wafer_sources.md:34` has a private-source audit and explicitly limits many sources to vocabulary, alarm/event names, or recipe context.
- Keep public WM811K labels as pattern evidence, not process RCA. The wafer source pack claim boundary says public WM811K labels are not verified process RCA labels (`src/kgtracevis/workflows/wafer_llm_source_pack.py:84`).

#### TEP

KGBuilder direct material:

- `/Users/hhm/code/KGBuilder/materials/tep_source_notes.md`
- Purpose: TEP process units, process/manipulated variables, fault scenarios, variable impact links, mechanisms, and evidence requirements.
- It cites the `mv-per` Tennessee Eastman dataset README, a Springer table, Skogestad control-variable-selection note, and Downs/Vogel original benchmark citation (`/Users/hhm/code/KGBuilder/materials/tep_source_notes.md:5`).
- It states process units, variable families, faults, and important measured/manipulated variables (`/Users/hhm/code/KGBuilder/materials/tep_source_notes.md:11`).
- It includes explicit process-unit-variable, fault-variable, anomaly-fault, mechanism, and evidence-requirement relations (`/Users/hhm/code/KGBuilder/materials/tep_source_notes.md:25`, `/Users/hhm/code/KGBuilder/materials/tep_source_notes.md:42`, `/Users/hhm/code/KGBuilder/materials/tep_source_notes.md:73`, `/Users/hhm/code/KGBuilder/materials/tep_source_notes.md:87`).
- `/Users/hhm/code/KGBuilder/profiles/tep_root_kgd_seed.json` adds versioned Root-KGD profiles and runtime mappings, including fault anchors, support targets, diagnostic variables, and rationale (`/Users/hhm/code/KGBuilder/profiles/tep_root_kgd_seed.json:1`).

KGTraceVis overlap:

- `docs/sources/tep_sources.md` records `tep_kg_variable_mapping`, `tep_kg_fault_labels_v3`, `rootlens_tep_runtime_projection`, and `kgtracevis_tep_producer_contract` with explicit boundaries (`docs/sources/tep_sources.md:5`).
- `data/kg/source_registry.csv` includes TEP_KG variable mapping, TEP_KG fault labels, KGTraceVis TEP producer contract, and RootLens TEP runtime projection (`data/kg/source_registry.csv:22`).
- `src/kgtracevis/kg/graph.py` defaults include `data/kg/tep_nodes.csv` and `data/kg/tep_edges.csv` (`src/kgtracevis/kg/graph.py:61`), which is the contamination risk the new compiler must avoid in strict generated-only validation.
- KGBuilder's TEP projector currently reads KGTraceVis Root-KGD reference assets when available and writes projected nodes/edges plus overlay CSVs (`/Users/hhm/code/KGBuilder/tep_root_kgd_projector.py:107`).

Merge recommendation:

- Treat KGBuilder `tep_source_notes.md` as a curated source-note unit for canonical KG cards/entities/edges.
- Treat `profiles/tep_root_kgd_seed.json` as a domain profile/runtime-view input, not as part of the core source-to-edge compiler loop.
- Merge KGTraceVis `tep_kg_variable_mapping` source and Root-KGD static asset schemas into the optional TEP runtime-view projection layer only.
- Do not let generated TEP canonical KG CSVs automatically append to `data/kg/tep_*` defaults. Generated-only validation must list exactly which node/edge files were loaded.

### KGTraceVis source systems and overlap

KGTraceVis currently has three source-material concepts that overlap with KGBuilder:

1. Legacy source registry:
   - `data/kg/source_registry.csv` uses `source_id,title,type,path_or_url,used_for,notes`.
   - `src/kgtracevis/kg_construction/source_loader.py:13` validates those columns.
   - It loads local text and explicitly rejects remote URL loading in `src/kgtracevis/kg_construction/source_loader.py:65`.
   - It is good as a registry/catalog, but not enough as a compiler artifact because it lacks chunk IDs, content hashes per unit/chunk, extraction metadata, and scenario in the header.

2. Source Library:
   - `src/kgtracevis/kg_construction/sources.py:16` defines `SourceLibraryRecord` with source ID, source type, scenario, path/url/text, metadata, timestamp, and provenance policy.
   - It can convert records into `KGConstructionSource` (`src/kgtracevis/kg_construction/sources.py:60`) and write audit-safe manifests (`src/kgtracevis/kg_construction/sources.py:126`).
   - This is closer to the source-unit boundary needed by `source_kg_compiler`.

3. Material Library:
   - `src/kgtracevis/service/kg_materials.py:161` defines URL/local/citation/extracted material registration.
   - `KGMaterialRecord` includes source URI, source kind, scenario, material type, metadata, extraction state, and a claim boundary (`src/kgtracevis/service/kg_materials.py:196`).
   - Extraction writes structured records and many audit artifacts, including raw IE responses, payload repairs, chunk results, extraction manifest, document map, prompt context, brainstorming artifacts, and suggestions (`src/kgtracevis/service/kg_materials.py:762`).
   - `prepare_kg_material_construction_build` converts selected extracted materials into `KGConstructionBuildRequest` inputs (`src/kgtracevis/service/kg_materials.py:732`).
   - `run_material_kg_construction_workflow` then calls the existing source-to-KG workflow and persists material metadata in summary/manifest (`src/kgtracevis/workflows/material_kg_construction.py:90`).

For `source_kg_compiler`, the best overlap is to reuse material/source-library metadata and manifests as input provenance, but bypass the existing DraftKG/alignment/review/publish machinery for the first clean compiler slice.

### Directly reusable KGBuilder materials

Directly reusable as source-note units:

- `/Users/hhm/code/KGBuilder/materials/mvtec_source_notes.md`
- `/Users/hhm/code/KGBuilder/materials/wafer_source_notes.md`
- `/Users/hhm/code/KGBuilder/materials/tep_source_notes.md`

These are directly ingested today and appear in KGBuilder's source registry with SHA-256 and byte counts (`/Users/hhm/code/KGBuilder/outputs/source_registry.csv:2`, `/Users/hhm/code/KGBuilder/outputs/source_registry.csv:3`, `/Users/hhm/code/KGBuilder/outputs/source_registry.csv:4`). They should be tagged as curated source notes, not raw industrial ground truth.

Reusable as traceability/raw materials:

- `/Users/hhm/code/KGBuilder/materials/source_docs/mvtec_ad.pdf`
- `/Users/hhm/code/KGBuilder/materials/source_docs/wafer_yield_prediction_spatial_variables.pdf`
- `/Users/hhm/code/KGBuilder/materials/source_docs/tennessee_eastman_dataset_readme.html`

KGBuilder does not ingest these automatically because only top-level `materials/` files are read (`/Users/hhm/code/KGBuilder/README.md:69`). In KGTraceVis, these should be represented as source units only if parser support and provenance IDs are explicit.

Reusable as runtime/profile references:

- `/Users/hhm/code/KGBuilder/profiles/tep_root_kgd_seed.json`
- `/Users/hhm/code/KGBuilder/outputs/domain_profiles.json`
- `/Users/hhm/code/KGBuilder/outputs/tep_root_kgd_view/`

These should not be merged into the core compiler loop. They belong in `domain_profiles/` and `runtime_views/` outputs, where the first slice can mark them `not_generated` or generate them explicitly later.

### KGTraceVis docs/data sources to merge

MVTec merge set:

- `docs/sources/mvtec_source_bundle/mvtec_ad_official_page.html`
- `docs/sources/mvtec_source_bundle/patchcore_arxiv_abs.html`
- optional ignored PDFs under `docs/sources/mvtec_source_bundle/raw/`
- `docs/sources/mvtec_source_bundle/manifest.json`
- `docs/sources/mvtec_sources.md`
- source IDs from `data/kg/source_registry.csv:17` through `data/kg/source_registry.csv:21`
- source pack specs from `src/kgtracevis/workflows/mvtec_llm_source_pack.py:143`

Wafer merge set:

- `docs/sources/wafer_sources.md`
- source IDs from `data/kg/source_registry.csv:9` through `data/kg/source_registry.csv:16`
- `data/examples/records/wm811k_records.jsonl`
- source pack specs from `src/kgtracevis/workflows/wafer_llm_source_pack.py:125`
- private-source summaries only after preserving the use limits in `docs/sources/wafer_sources.md:34`

TEP merge set:

- `docs/sources/tep_sources.md`
- source IDs from `data/kg/source_registry.csv:22` through `data/kg/source_registry.csv:25`
- KGTraceVis Root-KGD assets under `data/kg/tep_root_kgd/` only for runtime-view projection/validation, not source-unit-to-edge compilation.
- KGBuilder `profiles/tep_root_kgd_seed.json` as versioned runtime profile input, not raw source material.

Cross-scenario merge set:

- `src/kgtracevis/kg/graph.py` contract and optional RCA columns should be used for CSV compatibility, but `DEFAULT_NODE_PATHS` / `DEFAULT_EDGE_PATHS` should not be loaded in strict generated-only validation.
- `docs/kg_construction.md:252` through `docs/kg_construction.md:300` records the current material-library claim boundary and artifact inventory; reuse the audit metadata ideas, not the old workflow chain.

### Cautions about unsupported causal claims

- MVTec has no verified factory root-cause labels in KGTraceVis. The project docs state MVTec paths are plausible explanations, not verified causes (`docs/kg_hardening_pipeline.md:8`) and material smoke paths must not publish plausible-cause/root-cause edges as facts (`docs/kg_construction.md:454`).
- KGBuilder `mvtec_source_notes.md` contains many explicit `HAS_PLAUSIBLE_CAUSE` lines. Those are useful for compiler testing and path generation, but should stay `review_status=auto`, conservative confidence, and evidence wording should say plausible/reviewable.
- Public WM811K labels are spatial defect-pattern classes, not process RCA labels. KGTraceVis wafer source pack says public WM811K labels are not verified process RCA labels (`src/kgtracevis/workflows/wafer_llm_source_pack.py:84`).
- Private wafer summaries can support low-confidence candidate investigation targets only at the exact pattern/mechanism edge level; KGTraceVis docs warn not to use many private manuals/logs/recipes as defect RCA without paired evidence (`docs/sources/wafer_sources.md:39`).
- TEP fault labels and Root-KGD seed/profile assets are benchmark/runtime support material, not online causal proof. `docs/sources/tep_sources.md:16` marks TEP fault-label-derived variable-support edges as `review_status=auto`.
- KGBuilder's TEP projector reads KGTraceVis Root-KGD assets if available (`/Users/hhm/code/KGBuilder/tep_root_kgd_projector.py:220`). That is useful for compatibility but dangerous for strict KGBuilder-only validation unless the validation report lists all loaded reference assets and has a generated-only mode.

## Caveats / Not Found

- `python3 ./.trellis/scripts/task.py current --source` returned `Current task: (none)`, so this research used the user-specified task path rather than a runtime active-task pointer.
- No `KGBuilder` source exists inside the KGTraceVis repository; all KGBuilder references are from the sibling checkout `/Users/hhm/code/KGBuilder`.
- I did not fetch live external webpages. The overlap analysis is based on local KGBuilder files, local KGTraceVis docs/source registries, and locally recorded URLs/manifests.
- KGBuilder's current `outputs/source_registry.csv` shows only three directly ingested top-level notes, despite additional traceability files in `materials/source_docs/`. Treat those raw docs as provenance candidates, not confirmed current KGBuilder inputs.
- Some KGTraceVis source pack specs point to URLs or optional local/binary files that may not exist in the checkout. The compiler should record missing/skipped material entries rather than silently substituting derived KG artifacts.
