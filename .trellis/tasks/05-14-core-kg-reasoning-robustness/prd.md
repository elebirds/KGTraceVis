# brainstorm: optimize core KG reasoning layer

## Goal

Make small, high-confidence robustness improvements to the unified KG reasoning
pipeline so sparse TEP KGs degrade transparently, native TEP RCA preserves
contribution-sensitive scoring and explanations, entity-linking ambiguity is
visible to callers, and graph/path ranking remains scenario-scoped.

## What I Already Know

* Work is in `/Users/hhm/code/KGTraceVis`.
* The user explicitly limited ownership to core, kg, two RCA workflow files, and
  a focused set of tests.
* Do not modify adapters/schema, producers, service/API, web, or KG construction
  files.
* Do not add unsupported industrial KG facts.
* Prefer hardening and tests over broad scoring redesign.

## Requirements

* Keep changes small and focused on unified KG reasoning robustness.
* Make sparse TEP KG behavior transparent rather than silently overclaiming.
* Preserve native RCA contribution-sensitive scoring and explanations.
* Surface entity-linking ambiguity where available.
* Maintain scenario-scoped graph/path ranking behavior.
* Respect existing KG evidence/source/review constraints.

## Acceptance Criteria

* [ ] Focused tests cover the selected robustness improvements.
* [ ] Required pytest target set passes.
* [ ] Required ruff target set passes.
* [ ] Required mypy target set passes.

## Definition of Done

* Tests added or updated for changed behavior.
* Lint and type checks pass for the requested target scope.
* No files outside the requested ownership/write scope are modified unless
  unavoidable and explicitly justified.

## Out of Scope

* Adapter/schema, producer, service/API, web, and KG construction changes.
* New industrial KG facts or broad scoring redesigns.
* Neo4j import/runtime changes.

## Technical Notes

* Curated backend specs are listed in `implement.jsonl`.
* Required verification commands are the exact pytest, ruff, and mypy commands
  from the user request.
