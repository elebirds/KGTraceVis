# Database Runtime

KGTraceVis now treats databases as the runtime infrastructure for interactive
analysis and review.

## Responsibility Split

```text
Neo4j
  KG nodes, KG edges, scenario-scoped graph traversal, path candidates

Postgres
  evidence cases, analysis runs, linked entities, consistency checks,
  correction candidates, ranked paths, feedback, KG edit drafts, review actions,
  artifacts, KG version metadata

CSV/JSON
  reproducible seed/import/export artifacts and paper outputs
```

Postgres stores stable references to Neo4j IDs such as `node.id`, `edge.edge_id`,
`scenario`, and `kg_version`. It should not duplicate the full graph.

## Scenario Boundary

Runtime KG queries should always scope dataset-specific analysis to the selected
dataset plus the shared layer:

```text
mvtec evidence -> shared + mvtec
wafer evidence -> shared + wafer
tep evidence   -> shared + tep
```

This keeps MVTec, wafer, and TEP evidence schema-compatible without allowing
unsupported cross-domain RCA paths.

## Local Startup

```bash
docker compose up -d neo4j postgres
uv run python scripts/init_postgres.py
uv run python scripts/import_kg.py
```

For a containerized backend plus initialized databases:

```bash
docker compose up --build
```

The Compose stack includes one-shot `postgres-init` and `kg-import` services so
the API starts after the runtime databases are initialized.
The API service and local analysis scripts load dataset-scoped KG snapshots from
Neo4j at runtime.

Use `--dry-run` on the initialization/import scripts to validate local files
without connecting to services:

```bash
uv run python scripts/init_postgres.py --dry-run
uv run python scripts/import_kg.py --dry-run
```

## Runtime Configuration

The local defaults are captured in:

```text
configs/neo4j.example.yaml
configs/database.example.yaml
docker-compose.yml
```

Environment variables override the YAML examples:

```text
NEO4J_URI
NEO4J_USER
NEO4J_PASSWORD
NEO4J_DATABASE
KGTRACE_POSTGRES_DSN
POSTGRES_HOST
POSTGRES_PORT
POSTGRES_DB
POSTGRES_USER
POSTGRES_PASSWORD
```

## API Runtime State

The FastAPI run-history and feedback endpoints use Postgres as the runtime
source of truth. `analysis_runs.run_id` is the public API run ID and is stored as
a UUID. Run detail responses are assembled from `evidence_cases`,
`analysis_runs`, `run_evidence_cases`, `linked_entities`,
`consistency_checks`, `correction_candidates`, `ranked_paths`, `artifacts`, and
`feedback_records`; there is no legacy filesystem runtime fallback and no
run-detail snapshot table.

Uploaded source files and generated visualization artifacts can still live under
the run artifact directory so the API can serve files, but list/detail/feedback
state should be queried from Postgres by default.
