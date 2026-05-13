# RootLens Dashboard Workflow Hardening

## Goal

Turn the foundation-first RootLens dashboard skeleton into a smoother, more
demonstrable upload-first workflow without expanding into the full KG management
studio.

The previous task established stable contracts and a React/Vite shell. This task
should harden usability, example-driven smoke paths, browser verification, and
small UI/state issues that make the dashboard easier to demo and build on.

## What I Already Know

- `c969efb Add RootLens dashboard foundation` added:
  - `GET /api/dashboard/bootstrap`;
  - rootlens run history under `runs/rootlens_sessions`;
  - dashboard-friendly `RunDetail` fields;
  - review feedback contract and stable `target_key`;
  - React + TypeScript + Vite client under `web/`.
- HTTP smoke already covered bootstrap, upload through Vite proxy, run history,
  and feedback submit.
- Browser-level interaction verification has not yet been completed.
- Full quality gates passed in the foundation task.

## Requirements

### Demo Workflow Hardening

- Make the first-run workflow clearer for a local user:
  - visible API connection/bootstrap state;
  - empty-state guidance for no runs or no selected run;
  - clear upload mode descriptions/accepted file expectations;
  - clear post-upload success/review feedback status.
- Add small affordances for loading bundled examples where feasible, or document
  exact example files to upload from the repo.
- Preserve the foundation-first architecture; do not move analysis logic into
  the frontend.

### Browser Smoke Verification

- Add a repeatable smoke verification path for the dashboard:
  - start API;
  - start Vite;
  - load the page;
  - verify key text/sections render;
  - exercise upload/history/review through either browser automation or an
    equivalent documented smoke command.
- If adding browser tooling is too heavy, add a lightweight script or documented
  command that verifies the same API/client contract without committing generated
  artifacts.

### UI Robustness

- Ensure text fits in compact panels and buttons at desktop and narrow widths.
- Add responsive behavior for the three-column layout.
- Avoid decorative marketing-style sections.
- Keep cards un-nested except for repeated list/detail items where useful.
- Keep visual style calm, operational, and scan-oriented.

### Documentation

- Update `docs/rootlens_dashboard.md` or README with:
  - local launch steps;
  - example upload files;
  - dashboard smoke verification;
  - known scope boundaries for review feedback and KG editing.

## Acceptance Criteria

- Dashboard can be started locally and renders the upload/history/detail shell.
- A user can follow docs to upload an example producer-record file and inspect
  paths/provenance.
- Review feedback success/failure is visible and uses stable `target_key`.
- Responsive layout remains usable on a narrow viewport.
- Verification includes backend quality gates and frontend typecheck/build.
- Browser or equivalent dashboard smoke is documented and run.

## Out Of Scope

- Full KG force-directed editor.
- LLM source-to-KG generation UI.
- Authentication/multi-user state.
- Major service API redesign.
- Paper-demo visual polish beyond basic professional usability.

## Technical Notes

- Main files expected to change:
  - `web/src/App.tsx`
  - `web/src/state.ts`
  - `web/src/styles.css`
  - `docs/rootlens_dashboard.md`
  - tests or smoke scripts only if useful.
- Existing endpoints should be reused.
