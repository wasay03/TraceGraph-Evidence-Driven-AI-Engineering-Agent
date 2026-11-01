# TraceGraph

Typed, ontology-first code knowledge graph for Python (FastAPI + SQLAlchemy 2.0 + Alembic + pytest),
with a reasoning engine that answers multi-hop, aggregate and negated queries with derivations, and a
what-if impact analyzer built on top of it.

## Layout

```text
tracegraph/
  main.py               composition root: app factory, lifespan, middleware, routers
  config/               Settings (TG_* environment variables)
  constants/            literals only: permissions, tiers, extractor versions, engine limits, impact classes
  core/                 Database (engine + transactions), JSON logging, request context
  errors/               error taxonomy (Errors.HTTP / Errors.Database / Errors.Domain) and handlers
  middleware/           request id + latency logging
  dependencies/         FastAPI DI: settings, session, containers, authentication, permissions
  containers/           RepositoryContainer and ServiceContainer (lazy, per request or job)
  routers/              HTTP boundary only: validation, auth, response shaping
  schemas/              request/response models
  interfaces/           ABCs for every repository, service and the workspace
  services/             business logic and orchestration
  repositories/         data access; every call is SELECT ... FROM tg_<fn>(...)
  models/               one SQLAlchemy table per file, with its indexes (used by Alembic only)
  ontology/             closed registry: node/edge types, validation, catalog serialisation
  extract/              extraction pipeline and passes (structure, resolve, sqlalchemy, fastapi,
                        alembic, sql strings, facts, pytest), typed writer, incremental scope
  engine/               query IR, RPQ compiler, in-memory snapshot, evaluator, answer contract, cache
  impact/               ChangeSpecs, overlays, rule packs, invariants, analyzer, report
  sandbox/              git workspace (commit checkout via git archive)
  workers/              background index worker (SKIP LOCKED job queue)
  cli/                  tg serve | worker | index | query | impact
sql/functions/<domain>/ one stored function per file; the file name is the function name
migrations/versions/    Alembic revisions; schema from models, functions from sql/functions
tests/                  sql, ontology, extract, engine (golden, property, metamorphic), impact, api
tests/fixtures/shop/    seeded FastAPI/SQLAlchemy repo used by tests and benchmarks
examples/               sample IR query and ChangeSpec files
```

## Layering

```text
Router -> ServiceContainer -> service -> RepositoryContainer -> repository -> stored function -> PostgreSQL
```

Dependencies only point downward. Routers receive a `ServiceContainer` through `Depends`; services get
repositories (and other services) by constructor injection; repositories receive the `AsyncSession` and
issue nothing but stored-function calls with bound parameters. Stored functions signal domain errors with
custom SQLSTATEs (`TG400`, `TG404`, `TG409`, `TG422`) that `UdfRepository` maps to the error taxonomy.

The extractor, engine and impact packages are pure domain code: they never touch the database and are
driven by services.

## Database changes

- Tables: edit or add a file in `tracegraph/models/` (one table per file, indexes in `__table_args__`),
  then `alembic revision --autogenerate -m "..."` and review the result.
- Stored functions: add or edit `sql/functions/<domain>/tg_<name>.sql` (`CREATE OR REPLACE FUNCTION`,
  one function per file), then create a revision that lists the file in `SQL_FUNCTIONS`. The template
  calls `apply_sql_functions` on upgrade and `drop_sql_functions` on downgrade. A changed function gets a
  new revision that re-applies its file; old revisions are never edited.

## Running

```bash
python -m venv venv && ./venv/bin/pip install -e ".[dev]"
export TG_DATABASE_URL=postgresql+psycopg://user@localhost:5432/tracegraph TG_API_KEY=change-me
./venv/bin/alembic upgrade head

./venv/bin/tg index tests/fixtures/shop --ref WORKTREE        # register + index inline
./venv/bin/tg impact 1 examples/make_discount_nullable.yaml   # readable impact report
./venv/bin/tg query 1 examples/endpoints_writing_orders.yaml  # Answer JSON with derivations
./venv/bin/tg serve & ./venv/bin/tg worker                    # HTTP API + background indexing
```

Tests expect a disposable database at `TG_TEST_DATABASE_URL`
(default `postgresql+psycopg://tg@localhost:55432/tracegraph_test`); they migrate it down and up.

## HTTP API

All routes except `/health` require `X-API-Key`.

| Method | Path | Purpose |
| --- | --- | --- |
| GET | `/ontology`, POST `/ontology/sync` | Registry and catalog sync state |
| POST/GET | `/repos`, GET `/repos/{id}` | Register and list local repositories |
| POST/GET | `/repos/{id}/snapshots` | Queue full or incremental indexing; list snapshots |
| GET | `/snapshots/{id}`, `/snapshots/{id}/validation` | Status, counts, coverage holes; CI validation query |
| POST | `/query`, GET `/answers/{handle}` | Typed IR query; stored Answer with derivations |
| POST | `/impact`, GET `/impact/{handle}` | ChangeSpecs to overlay and impact report |
| POST | `/invariants/check` | INV-002 to INV-008 on a snapshot |

## Status against the PRD milestones

| Milestone | State |
| --- | --- |
| M1 registry, store, core extraction | Done. Resolution is an in-house resolver instead of scip-python; structure uses stdlib `ast` instead of LibCST. |
| M2 domain extraction and incremental | Done. Schema is derived by statically replaying Alembic ops rather than introspecting a live database; coverage-based TESTS edges are not implemented. |
| M3 reasoning engine | Done except the textual DSL and Datalog rule packs; the JSON IR is the interface. |
| M4 impact and invariants | Done for seven ChangeSpec kinds and INV-001 to INV-008; rule packs are Python, not DSL files. |
| M5 tools, agent, sandbox | Not started. |
| M6 benchmark and ablations | Not started. |
| M7 polish (UI, OpenTelemetry, Docker Compose) | Not started. |
