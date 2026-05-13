# RootLens Source To KG Draft Generation

## Goal

Add the foundation for source-grounded KG generation in the dashboard: a user
can paste source text or structured triple lines, generate candidate KG edge
drafts, inspect provenance/confidence, and keep the output as reviewable
candidates rather than verified facts.

## Requirements

1. Add a read-only/non-mutating API endpoint for source-to-KG draft generation.
2. Support a deterministic `heuristic` provider that can run without external
   LLM credentials.
3. Parse structured lines in the form:
   `head,relation,tail,scenario[,evidence]`
4. Assign conservative confidence, source, evidence, weight, and
   `review_status=auto`.
5. Return schema-compatible candidate edges with stable edge IDs.
6. Add a KG Studio UI section to submit source text and display generated
   candidate edges.
7. Keep LLM provider integration out of scope for this commit, but preserve a
   provider field so future LLM output can use the same contract.
8. Extend smoke/tests/docs.

## Out of Scope

- Calling a remote LLM provider.
- Writing generated candidates to KG CSV files.
- Promoting candidates into `data/kg/`.
- Entity/node creation beyond candidate edge preview.

## Acceptance Criteria

- [ ] Structured source lines produce candidate edge drafts.
- [ ] Generated edges include source/evidence/confidence/weight/review status.
- [ ] UI can generate and inspect candidates without a selected run.
- [ ] Generated candidates are clearly marked as draft/candidate only.
- [ ] Quality gates pass.

