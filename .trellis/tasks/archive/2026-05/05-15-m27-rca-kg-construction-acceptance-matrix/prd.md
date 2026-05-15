# M27 RCA-KG Construction Acceptance Matrix

## Goal

Add a concise, executable acceptance matrix for the rebuilt RCA-oriented KG
construction system so the final state is inspectable without reading commit
history.

## Scope

- Document the implemented pipeline, required artifacts, validation commands,
  product/API entry points, LLM boundary, TEP boundary, and remaining non-goals.
- Tie acceptance rows to concrete files, commands, and report artifacts.
- Keep the document honest: no claim that LLM output is reviewed fact, no claim
  that TEP_KG schema is the global schema, no claim that real Neo4j writes run
  without explicit confirmation.

## Acceptance

- New docs page exists under `docs/`.
- `docs/kg_construction.md` links to it.
- Quality gates for docs-touching change pass at least lint/type/tests smoke
  already run in this session; rerun focused docs-neutral gates before commit.
