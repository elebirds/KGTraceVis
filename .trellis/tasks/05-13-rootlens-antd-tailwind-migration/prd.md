# RootLens AntD + Tailwind UI Migration

## Goal

Migrate the RootLens frontend visual layer from hand-written primitive controls
to a more credible product UI stack:

- Ant Design for atomic and complex components;
- Tailwind CSS for page layout, spacing, and responsive composition;
- minimal project CSS only for domain-specific graph visuals and app-level
  polish.

The migration should preserve existing API contracts and workflow behavior.

## Requirements

1. Install and configure:
   - `antd`;
   - `@ant-design/icons`;
   - `tailwindcss`;
   - `@tailwindcss/vite`.
2. Import AntD reset styles and Tailwind CSS entry.
3. Configure Vite with the Tailwind plugin.
4. Refactor frontend surfaces to use AntD where appropriate:
   - app shell: `Layout`, `Menu`;
   - page cards: `Card`;
   - actions: `Button`;
   - status: `Alert`, `Tag`, `Badge`;
   - forms: `Form`, `Input`, `Select`, `InputNumber`, `Upload`;
   - lists/tables: `List`, `Table`, `Descriptions`, `Statistic`;
   - segmented/tab-like surfaces where useful.
5. Use Tailwind classes for macro layout and spacing, not to fight AntD internals.
6. Keep existing business logic, API calls, and state transitions intact.
7. Keep force graph/domain visual classes where AntD does not help.
8. Update docs to state the frontend stack.
9. Run quality gates.

## Out of Scope

- Figma implementation.
- Full component folder extraction.
- Rewriting API contracts.
- Changing KG/case analysis behavior.

## Acceptance Criteria

- [x] Dashboard shell uses AntD `Layout/Menu`.
- [x] Upload, review, and KG forms use AntD controls.
- [x] Overview metrics use AntD cards/statistics.
- [x] Candidate/path/KG lists use AntD list/table-like components.
- [x] Tailwind powers page layout classes.
- [x] Frontend typecheck/build and dashboard smoke pass.

## Completion Notes

- Migrated the RootLens shell to a top-navigation dashboard layout.
- Added Ant Design and Tailwind CSS through the Vite plugin.
- Preserved existing FastAPI contracts, upload flows, run history, case
  analysis, KG Studio, graph review, and feedback behavior.
- Verified with frontend build, dashboard smoke, pytest, examples, ruff, and
  diff hygiene.
