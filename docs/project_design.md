# Project Design

KGTraceVis is organized as a reusable core library with separate script and app clients.

The core package under `src/kgtracevis/` owns schema validation, KG construction,
entity linking, consistency checking, correction generation, path ranking, noise
injection, metrics, and feedback-compatible result models.

Scripts under `scripts/` should only orchestrate these modules. Streamlit and any
future API service should call the same pipeline APIs.
