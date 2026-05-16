# implement: source KG compiler evaluation observability

## Goal

Add default-on progress logging and small-batch observability to the source KG compiler evaluation command so long live runs show where time is spent, especially around source compilation and LLM calls.

## What I already know

* A real command, `uv run python scripts/evaluate_source_kg_compiler.py --output-dir runs/source_kg_compiler_evaluation/live_full --overwrite`, ran for 12 minutes with no output.
* The user wants logs by default and a `--quiet` opt-out.
* Existing uncommitted evaluation files must be preserved and extended, not reverted.
* RootLens-unrelated files must not be changed.

## Requirements

* Add default-on staged logging to `scripts/evaluate_source_kg_compiler.py`.
* Logs should include configuration summary, compile start, source unit/card/entity/edge/domain profile phases or close equivalents, sample analysis, baseline comparison, and report output paths.
* Add `--quiet` to suppress progress output.
* If needed, minimally add a progress callback or logger path through the source KG compiler workflow/compiler.
* Around each LLM `complete_json` call, log stage, item or batch, elapsed time, cumulative calls, and cumulative tokens.
* Do not log prompts, API keys, or sensitive request bodies.
* Add a quick smoke path such as `--limit-sources N`; if implemented, cover it in tests.
* Add or update tests verifying verbose output contains key stages and quiet suppresses progress.
* Keep the existing strict generated-only test behavior.

## Acceptance Criteria

* [ ] Default evaluation CLI prints meaningful progress for long-running work.
* [ ] `--quiet` suppresses progress logs.
* [ ] LLM call progress includes stage/item/elapsed/calls/tokens without prompts or secrets.
* [ ] A small-batch option is available and tested.
* [ ] Existing generated-only evaluation behavior remains covered.
* [ ] Ruff, mypy, and target pytest pass or any blocker is documented.

## Out of Scope

* Refactoring unrelated RootLens files.
* Changing KG extraction semantics beyond adding observability and source limiting.
* Printing prompt contents or provider credentials.

## Technical Notes

* Start from existing uncommitted files:
  * `scripts/evaluate_source_kg_compiler.py`
  * `src/kgtracevis/workflows/source_kg_compiler_evaluation.py`
  * `tests/test_source_kg_compiler_evaluation.py`
* Search before touching compiler internals to find the existing source KG compiler and LLM call path.
