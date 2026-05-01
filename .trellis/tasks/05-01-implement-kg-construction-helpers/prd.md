# Implement KG Construction Helpers

## Goal

Turn the KG construction placeholder modules into a small source-constrained
helper layer for loading source records, extracting candidate nodes/triples,
assigning confidence, cleaning/deduplicating candidates, and exporting KG CSVs.

The task should support curated v0 workflows without introducing unsupported
industrial facts or a large extraction framework.

## Requirements

- Implement source registry/text loading helpers.
- Implement candidate entity extraction from provided source records/text.
- Implement candidate triple extraction from structured records only; no
  free-form industrial causal invention.
- Implement deterministic confidence assignment by source type.
- Implement triple cleaning/deduplication with reviewed-edge protection.
- Implement KG CSV export using the existing node/edge column contracts.
- Update `scripts/build_kg.py` to validate/export or summarize curated KG files
  without duplicating core logic.
- Keep all reusable logic under `src/kgtracevis/kg_construction/`.

## Acceptance Criteria

- [x] Tests cover source registry loading.
- [x] Tests cover candidate entity/triple extraction from structured records.
- [x] Tests cover confidence assignment by source type.
- [x] Tests cover node/edge deduplication and reviewed-edge overwrite
  protection.
- [x] Tests cover CSV export with required columns.
- [x] `scripts/build_kg.py` runs locally.
- [x] `uv run --extra dev pytest` passes.
- [x] `uv run --extra dev ruff check .` passes.
- [x] `uv run --extra dev mypy src tests scripts` passes.
- [x] `uv run python scripts/run_examples.py` passes.

## Out Of Scope

- No LLM extraction call.
- No web scraping.
- No new industrial facts added to checked-in KG.
- No Neo4j import behavior.
- No large dataset ingestion.

## Technical Notes

- Expected implementation files:
  - `src/kgtracevis/kg_construction/source_loader.py`
  - `src/kgtracevis/kg_construction/candidate_entity_extractor.py`
  - `src/kgtracevis/kg_construction/candidate_triple_extractor.py`
  - `src/kgtracevis/kg_construction/confidence_assigner.py`
  - `src/kgtracevis/kg_construction/triple_cleaner.py`
  - `src/kgtracevis/kg_construction/export_kg_csv.py`
  - `scripts/build_kg.py`
  - focused tests under `tests/`
