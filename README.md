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
  core/                 Database (engine + transactions), JSON logging, request context, tracing
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
  engine/               query IR, RPQ compiler, in-memory snapshot, evaluator, answer contract, cache,
                        textual DSL, stratified Datalog rules, overlay/diff operators, why-not abduction
  rules/                derive/*.tg rule packs and invariants/*.tg written in the DSL
  impact/               ChangeSpecs, overlays, rule packs, invariants, analyzer, report
  agent/                state machine, phase runner, artifacts, plan rules, claim checker, verification ladder
  tools/                tool registry (phase/scope/budget gating) and the tool catalog
  sandbox/              git checkout and per-run worktrees with fixed command templates
  workers/              background index worker (SKIP LOCKED job queue)
  bench/                benchmark tasks, metrics, impact and agent runners
  ui/static/            web UI: no-build ES modules, vendored Cytoscape (served at /ui)
  utilities/llm/        one LLM client interface; Gemini and Anthropic adapters, key fallback, throttle
  cli/                  tg serve | worker | index | query | impact | run | resume | bench
sql/functions/<domain>/ one stored function per file; the file name is the function name
migrations/versions/    Alembic revisions; schema from models, functions from sql/functions
tests/                  sql, ontology, extract, engine (golden, property, metamorphic), impact, api
tests/fixtures/shop/    seeded FastAPI/SQLAlchemy repo used by tests and benchmarks
examples/               sample IR query and ChangeSpec files
bench/suites/           benchmark suites (seeded.yaml); bench/reports/ holds generated reports
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
./venv/bin/tg bench bench/suites/seeded.yaml                  # impact benchmark, no LLM
./venv/bin/tg run 1 "Add a CANCELLED order status"            # agent run (calls the configured LLM)
./venv/bin/tg resume 1 --extra-llm-calls 5                    # continue a failed or exhausted run
```

Open `http://localhost:8000/ui/` and enter `TG_API_KEY`. The views are Repositories (register, index,
snapshots, coverage holes, source), Impact (build ChangeSpecs, findings with derivation graphs,
obligations, invariant diff), Query (IR or DSL with examples, witness paths), Ontology, and Runs (start,
approve, edit or reject plans, verification ladder, partial reports, audit log). Only starting a run
calls the model.

Or `docker compose up` (Postgres, migrations, API on :8000, worker); repositories under `TG_REPOS_DIR`
(default `tests/fixtures`) are mounted read-only at `/repos`.

### Agent LLM

The agent talks to its model through one utility, `tracegraph/utilities/llm`
(`create_llm_client(settings)`), with an adapter per provider behind `ILlmClient`. Pick the provider and
model with environment variables:

```bash
export TG_LLM_PROVIDER=gemini          # gemini | anthropic (default)
export TG_LLM_MODEL=gemini-3.5-flash-lite  # required for gemini; anthropic defaults to claude-opus-5-5
export TG_LLM_API_KEY=...              # or leave unset and use GEMINI_API_KEY / ANTHROPIC_API_KEY
export TG_LLM_API_KEY_FALLBACK_1=...   # optional, tried when a key is invalid, forbidden or out of quota
export TG_LLM_API_KEY_FALLBACK_2=...
export TG_LLM_MAX_OUTPUT_TOKENS=16000
```

- Gemini (`google-genai`): manual function calling (automatic calling disabled, the state machine owns
  the loop), temperature 0, SDK retries on 408/429/5xx; the model's own turns are replayed unchanged so
  thought signatures survive multi-turn tool use; safety blocks surface as refusals.
- Anthropic: pinned effort, adaptive thinking, server-side refusal fallback; this model rejects sampling
  parameters, so there is no temperature setting.

### Queries and rules

Queries are typed IR (JSON) or DSL text. The DSL compiles to stratified, semi-naive rule evaluation with
why-provenance; `not P scope S` is three-valued (TRUE only where the region has no coverage holes,
otherwise UNKNOWN), and aggregates report `lower_bound` under holes.

```json
{"op": "dsl", "rule_pack": "core", "text": "?- untested_writer(E)."}
{"op": "dsl", "text": "?- aggregate(T, count_distinct(E)) :- Endpoint(E), HANDLED_BY(E, H), reach(H, F, \"CALLS*\"), WRITES_TO(F, T), Table(T) order by 2 desc limit 10."}
{"op": "why_not", "expected": "app.services.calculate_total", "query": {"op": "reach", "input": {"op": "select", "type": "Endpoint", "where": {"key": "POST /orders"}}, "rpq": "HANDLED_BY . CALLS*", "max_hops": 1}}
{"op": "diff", "query": {"op": "select", "type": "Column", "where": {"nullable": true}}, "changes": [{"kind": "make_column_nullable", "column": "orders.total"}]}
```

Operators: select, resolve, expand, reach, paths, match, union, intersect, minus, not_exists, forall,
aggregate, rank, scc, derive, check, with_overlay, diff, why_not, dsl.

### Tracing

`TG_OTEL_EXPORTER=console` prints OpenTelemetry spans, and `otlp` sends them to
`OTEL_EXPORTER_OTLP_ENDPOINT` (install `.[otel]`). Spans nest run, phase, tool call, engine operator and
stored-function call. With the variable unset, tracing does nothing.

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
| POST/GET | `/runs`, `/runs/{id}` | Start or list agent runs (mode, config B0-A4); state, artifacts, audit log |
| POST | `/runs/{id}/retry` | Resume a failed or budget-exhausted run, optionally raising its LLM call cap |
| GET | `/snapshots/{id}/source` | Source lines of a file at the snapshot's commit (for the UI) |
| POST | `/runs/{id}/approval`, `/runs/{id}/clarify` | Human gate: approve, edit or reject a plan; answer an ambiguity |

## Status against the PRD milestones

| Milestone | State |
| --- | --- |
| M1 registry, store, core extraction | Done. Resolution is an in-house resolver instead of scip-python; structure uses stdlib `ast` instead of LibCST. |
| M2 domain extraction and incremental | Done. Schema comes from statically replaying Alembic ops, not from a live database; coverage-based TESTS edges are not implemented. |
| M3 reasoning engine | Done: all PRD 7.2 operators, the textual DSL with stratified rules, three-valued negation, lower-bound aggregates. The DSL parser is hand-written (no lark). |
| M4 impact and invariants | Done for 12 ChangeSpec kinds and INV-001 to INV-008. The impact rule packs are Python; `rules/` holds DSL packs and INV-002 in DSL, tested equal to the Python check. |
| M5 tools, agent, sandbox | Done: 40 tools across six phases. The sandbox is a git worktree with fixed command templates, not a network-isolated container. Type-check and migration round-trip rungs report unavailable, and lint needs ruff installed. |
| M6 benchmark and ablations | The question-only impact benchmark runs on a 17-task seeded suite, 4 of them hole tasks (`bench/reports/seeded-impact.md`). One real A4 agent run on Gemini completed and passed every executed rung. The suite is not frozen, there are no open-source tasks, and the B0..A4 x 3 ablation has not been run because it needs model quota. |
| M7 polish | Web UI, OpenTelemetry tracing, Docker Compose (not run here). |
