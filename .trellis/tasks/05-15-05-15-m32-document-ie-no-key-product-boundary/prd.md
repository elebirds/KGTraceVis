# M32 Document IE No-Key Product Boundary

## Problem

KGTraceVis already separates LLM-backed document IE from KG publish/review, but
the material extraction product path still defaults to OpenAI-backed extraction.
Without an LLM key, the backend can run tests with injected clients and the
construction pipeline can replay offline fixtures, but the material API/UI do
not make that no-key path explicit.

## Goal

Make document IE extraction usable and auditable without an LLM key while
preserving the adapter-not-authority boundary:

- Users can choose an offline fixture provider in the material extraction API/UI.
- Offline and OpenAI extraction both write structured records, chunk results,
  manifest provider metadata, and candidate/review boundaries.
- The no-key path requires source-attached fixture payloads and never silently
  invents KG rows.
- Tests prove provider selection, manifest metadata, and KG Studio request
  contracts.

## Non-Goals

- Do not add a free-form heuristic extractor that invents candidate facts.
- Do not publish document IE output directly to runtime KG.
- Do not add a new top-level service or storage system.
- Do not require a real OpenAI key in tests or smoke runs.

## Acceptance

- `KGMaterialExtractionRunRequest.provider` supports `openai` and
  `offline_fixture`.
- `offline_fixture` uses material metadata fixture payload/path and fails with a
  clear validation error when no fixture exists.
- Extraction state, extraction runs, artifacts, and manifests record the actual
  provider/extractor name.
- KG Studio material workflow exposes provider selection and sends it through
  the typed client.
- Existing gates pass, with focused tests for no-key material extraction.
