# implement: real long-context and agentic document understanding

## Goal

Move Document Understanding Mode from a safe deterministic scaffold to a real,
testable long-context / agentic reader subsystem while preserving KGTraceVis
claim boundaries: LLM/agent outputs remain advisory planning, prompt context,
cross-chunk proposals, and review-only candidates until explicit review promotes
them into KG construction staging.

## What I already know

* Previous work added construction artifact plumbing for:
  `document_understanding_manifest.json`, `document_map.json`,
  `chunk_prompt_context.jsonl`, and `cross_chunk_proposals.jsonl`.
* Current tests pass: 354 passed, and RCA-KG smoke covers five paths.
* Existing `long_context` / `agentic` behavior is deterministic advisory map
  generation; it does not call an LLM and does not run a multi-step reader.
* The existing safe boundary is correct and must remain:
  document context can guide chunk IE, but DraftKG candidate evidence must
  still come from the current chunk.

## Requirements

* Add a `DocumentUnderstandingClient` protocol for document-map generation.
* Add an OpenAI-compatible long-context client with JSON-schema response
  handling for document maps.
* Add an offline fixture document-understanding client for deterministic tests.
* Add an `AgenticDocumentReader` or equivalent orchestrator that performs a
  multi-step read/plan/summarize/propose flow over parsed chunks and records
  step artifacts.
* Make `long_context` use the document-understanding client when configured,
  with deterministic fallback only for no-client/offline-safe runs.
* Make `agentic` distinct from `long_context`: it should produce step records
  and merge chunk/section observations into the same document map contract.
* Make chunk prompt context chunk-specific, not just generic document-level
  term slices.
* Generate cross-chunk proposals automatically from document-map relation hints
  or client output, while keeping validation/review-only behavior.
* Define and implement an accepted cross-chunk proposal staging path that can
  become DraftKG/edge staging only after explicit review, not during initial
  extraction.
* Add tests that use offline fixtures/fake clients only; no live LLM calls in CI.

## Acceptance Criteria

* [x] Default `chunk` mode remains compatible.
* [x] `long_context` can consume an injected/fake LLM document-understanding
  client and write client-derived document map content.
* [x] `agentic` writes multi-step reader artifacts and is not just an alias of
  `long_context`.
* [x] Chunk prompt context rows are scoped to the specific chunk.
* [x] Cross-chunk proposals can be auto-generated and validated from map output.
* [x] Invalid cross-chunk proposals are rejected deterministically.
* [x] Valid cross-chunk proposals enter review queue and never publish directly.
* [x] Accepted cross-chunk proposal review has a defined staging path into
  candidate edge/DraftKG artifacts without bypassing review.
* [x] Agentic document reading uses a deterministic retrieval/section plan and
  records selected chunk IDs per reader step.
* [x] Reviewed cross-chunk proposal RCA staging remains off by default and can
  only be enabled through explicit capped review-acceptance policy metadata.
* [x] Full pytest, examples, lint/type checks pass.

## Out of Scope

* Live network LLM calls in tests.
* Direct Neo4j publication from document understanding.
* Any claim that document-level summaries are reviewed industrial facts.

## Technical Notes

* Starting from clean `main` at `e095838`.
* Implemented `DocumentUnderstandingClient`,
  `OpenAICompatibleDocumentUnderstandingClient`, offline fixture replay,
  `AgenticDocumentReader`, chunk-scoped prompt context, proposal generation from
  relation hints, and review-time cross-chunk edge staging.
* Follow-up iteration added deterministic retrieval-backed agentic chunk
  selection, precise DU payload validation errors, and explicit capped
  review-only RCA opt-in policy for accepted cross-chunk proposals.
* Verification completed:
  `uv run --extra dev pytest -q` -> 360 passed;
  `uv run --extra dev ruff check .` -> passed;
  `uv run --extra dev mypy src tests scripts` -> passed;
  `uv run python scripts/run_examples.py` -> 4 examples validated;
  `uv run --extra dev pytest tests/test_kg_construction_smoke_workflow.py -q`
  -> 3 passed; `npm run typecheck` in `web/` -> passed.
