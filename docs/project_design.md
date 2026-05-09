# Project Design

KGTraceVis is organized as a reusable core library with separate script and app clients.

The core package under `src/kgtracevis/` owns schema validation, KG construction,
entity linking, consistency checking, correction generation, path ranking, noise
injection, metrics, and feedback-compatible result models.

Scripts under `scripts/` should only orchestrate these modules. The FastAPI
service under `src/kgtracevis/service/` and the React app under `web/` should
also call the same pipeline APIs. Streamlit remains a lightweight legacy demo,
not the primary product shell.
