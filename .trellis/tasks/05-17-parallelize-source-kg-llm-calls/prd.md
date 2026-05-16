# brainstorm: parallelize source KG LLM calls

## Goal

Reduce source KG compiler wall-clock time by running independent LLM calls within
the knowledge-card, entity, and edge stages concurrently while preserving
deterministic artifact ordering and existing KG contracts.

## What I already know

* The user wants the default LLM concurrency to be 4.
* Current compiler stages are sequential, but calls inside `knowledge_cards`,
  `entities`, and `edges` are independent enough to parallelize.
* Stage ordering must remain `source_units -> knowledge_cards -> entities ->
  edges -> domain_profiles`.

## Requirements

* Add a configurable `llm_concurrency` option with default `4`.
* Keep CLI, workflow, and API behavior aligned.
* Preserve deterministic merge/upsert order after concurrent LLM responses.
* Keep progress logs useful for long-running jobs.

## Acceptance Criteria

* [ ] `scripts/compile_source_kg.py` and `scripts/evaluate_source_kg_compiler.py`
  expose `--llm-concurrency`, defaulting to 4.
* [ ] Service build requests accept `llm_concurrency`, defaulting to 4.
* [ ] Tests cover bounded concurrent calls and default CLI propagation.
* [ ] Focused pytest and lint checks pass.

## Out of Scope

* Splitting the single global domain-profile prompt.
* Retrying/rate-limit backoff beyond existing provider errors.
