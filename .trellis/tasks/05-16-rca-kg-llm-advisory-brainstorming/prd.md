# brainstorm: RCA KG LLM advisory brainstorming pipeline

## Goal

Extend the RCA-oriented KG construction pipeline so LLM-backed components can
help with document understanding, candidate suggestion, ambiguity explanation,
profile gap discovery, semantic policy brainstorming, and RCA hypothesis review
without owning graph writes or bypassing source grounding.

## What I already know

* Existing construction supports material/source KG construction, chunk/long
  context/agentic document understanding, offline fixture and OpenAI-compatible
  document understanding clients, chunk-scoped IE context, cross-chunk relation
  proposals, reviewed cross-chunk edge staging, capped RCA staging policies, and
  KG Studio controls for understanding mode/provider.
* Brainstorming must be an independent optional axis, not a fourth
  `document_understanding_mode`.
* LLM output in alignment, semantic projection, and RCA policy stages is
  advisory only. Graph-changing or RCA-changing output must enter the review
  queue and remain auditable through artifacts and manifests.
* Initial implementation should support `hypothesis_influence="review_only"`;
  `prompt_context` and `profile_suggestions` should be present in request,
  schema, and manifest as future extension points.

## Requirements

* Add request/config fields for `hypothesis_mode`, `hypothesis_provider`,
  `hypothesis_influence`, `hypothesis_fixture_path`, and
  `hypothesis_payload`.
* Add a separated brainstorming module with data models, deterministic fallback,
  offline fixture client, and OpenAI-compatible client.
* Write brainstorming artifacts:
  `brainstorm_hypotheses.jsonl`, `brainstorm_evidence_tasks.jsonl`,
  `brainstorm_profile_gaps.json`, `brainstorm_review_items.json`, and
  `hypothesis_brainstorming_manifest.json`.
* Merge brainstorming, alignment suggestion, semantic suggestion, and profile
  gap review items into the existing review queue.
* Keep deterministic profile/mapping/semantic projection authoritative.
  Suggestions must not mutate canonical IDs, profile, published KG, propagation
  flags, or RCA scores before review.
* Add review behavior for hypothesis, causal chain, missing evidence, profile
  gap, alias mapping, variable mapping, and semantic policy candidates.
* Preserve current cross-chunk acceptance behavior and apply existing capped RCA
  policy constraints when accepted semantic/RCA suggestions are eligible.
* Expose independent KG Studio controls for hypothesis mode/provider/influence
  and offline fixture path.
* Update KG construction docs, RCA architecture docs, and acceptance matrix.

## Acceptance Criteria

* [ ] Hypothesis config validation covers deterministic fallback, offline
  fixture path/payload validation, and precise invalid payload errors.
* [ ] Brainstorm artifacts and manifest are written and manifest records
  mode/provider/influence.
* [ ] Mixed mode works with `document_understanding_mode=agentic` and
  `hypothesis_mode=brainstorm`; both document understanding and brainstorming
  artifacts exist, chunk IE stays chunk-scoped, and review items merge.
* [ ] Accept/reject behavior for brainstorm review items records decisions and
  only stages causal-chain edges when validation passes.
* [ ] Alias/variable/semantic suggestions enter review queue but do not affect
  canonical IDs or RCA propagation before review.
* [ ] Accepted semantic/RCA suggestions affect only allowed capped fields.
* [ ] Smoke path includes a no-key brainstorm/offline path while TEP smoke stays
  passing.
* [ ] `uv run pytest -q`, RCA KG smoke, and `cd web && npm run build` pass or
  any environmental blocker is recorded.

## Definition of Done

* Tests added/updated for backend workflow, review behavior, material service,
  and frontend contracts where applicable.
* Docs updated for architecture, KG construction operation, and acceptance
  boundaries.
* The review queue remains the boundary between LLM suggestions and KG mutation.
* Generated artifacts are manifest-recorded, diffable, and offline-testable.

## Out of Scope

* Letting LLMs directly publish facts, mutate profile files, rewrite historical
  KG rows, or enable high-confidence RCA propagation.
* Implementing full prompt-context or profile-suggestions influence behavior
  beyond schema/manifest placeholders.
* Training or adding new RCA models.

## Technical Notes

* Main backend touchpoints discovered so far:
  `src/kgtracevis/service/kg_materials.py`,
  `src/kgtracevis/kg_construction/document_extraction.py`,
  `src/kgtracevis/workflows/source_kg_construction.py`,
  `src/kgtracevis/workflows/material_kg_construction.py`,
  `src/kgtracevis/workflows/kg_construction_review.py`,
  `src/kgtracevis/kg_construction/review_queue.py`, and
  `src/kgtracevis/kg_construction/models.py`.
* Main frontend touchpoints discovered so far:
  `web/src/api/contracts.ts`,
  `web/src/features/kg-studio/KGStudioPages.tsx`, and
  `web/src/app/App.tsx`.
* Relevant specs read: backend workflow architecture, error handling, quality,
  database guidelines, and frontend workbench UI guidelines.
