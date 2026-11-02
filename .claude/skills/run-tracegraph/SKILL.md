---
name: run-tracegraph
description: Run, start, launch or screenshot TraceGraph (FastAPI API, background worker and the /ui web app) against a throwaway Postgres, index the shop fixture, smoke-test the API with curl, drive every UI view in headless Chromium, and run the test suite.
---

# Run TraceGraph

TraceGraph is a FastAPI app (`tg serve`) with a background index worker (`tg worker`) and a no-build web UI at
`/ui`, all backed by Postgres stored functions. The agent path is: a throwaway Postgres cluster on TCP only,
`alembic upgrade head`, `tg index` the shop fixture, `tg serve` + `tg worker` in the background, `curl` for the
API, and `.claude/skills/run-tracegraph/driver.py` (Playwright, headless Chromium) for the UI.

All paths are relative to the repository root. Nothing below calls an LLM. Only starting an agent run does
(`tg run`, `POST /runs`, or "Start run" in the UI), and the configured keys are free-tier Gemini keys, so don't
start one unless you're asked to.

## Prerequisites

Verified on Ubuntu 25.10 with PostgreSQL 17 server binaries at `/usr/lib/postgresql/17/bin` and the project
venv already at `./venv` (`python -m venv venv && ./venv/bin/pip install -e ".[dev]"`).

Playwright lives in its own venv so it never touches the project's dependencies:

```bash
W=/tmp/tg-run            # any writable scratch dir; keep it short-ish
python3 -m venv $W/pw && $W/pw/bin/pip install -q playwright
PLAYWRIGHT_BROWSERS_PATH=$W/pw-browsers $W/pw/bin/playwright install chromium
```

## Start the stack

```bash
P=/usr/lib/postgresql/17/bin
$P/initdb -D $W/pgdata -U tg --auth=trust -E UTF8 --locale=C.UTF-8 > $W/initdb.log 2>&1
$P/pg_ctl -D $W/pgdata -o "-p 55433 -k ''" -l $W/pg.log start
$P/createdb -h localhost -p 55433 -U tg tracegraph

export TG_DATABASE_URL=postgresql+psycopg://tg@localhost:55433/tracegraph TG_API_KEY=dev-key \
       TG_LOG_LEVEL=WARNING TG_WORKSPACE_DIR=$W/ws
./venv/bin/alembic upgrade head
./venv/bin/tg index tests/fixtures/shop --ref WORKTREE      # fresh DB: repository id 1, snapshot seq 1

nohup ./venv/bin/tg serve --port 8766 > $W/serve.log 2>&1 &
nohup ./venv/bin/tg worker > $W/worker.log 2>&1 &
for i in $(seq 1 30); do curl -sf localhost:8766/health >/dev/null && break; sleep 0.5; done
```

## Run (agent path)

API smoke test with curl (every route except `/health` needs `X-API-Key`):

```bash
curl -s localhost:8766/health                                   # {"status":"ok","database":"ok",...}
curl -s -o /dev/null -w "%{http_code}\n" localhost:8766/repos   # 401 without a key
curl -s -H "X-API-Key: dev-key" localhost:8766/repos            # the shop repository
```

UI: the driver logs in with the key and walks every view. It checks snapshot validation, an impact simulation
with its derivation graph and source, invariants, every query example, the runs and ontology views, and
overflow at phone width. It saves screenshots and exits 1 if anything goes wrong (console errors, page
errors, query errors, overflow):

```bash
PLAYWRIGHT_BROWSERS_PATH=$W/pw-browsers $W/pw/bin/python .claude/skills/run-tracegraph/driver.py smoke \
  --base http://localhost:8766/ui/ --key dev-key --repo 1 --out $W/shots
```

To screenshot one view, for example after changing it:

```bash
PLAYWRIGHT_BROWSERS_PATH=$W/pw-browsers $W/pw/bin/python .claude/skills/run-tracegraph/driver.py shot "#/ontology" \
  --base http://localhost:8766/ui/ --key dev-key --wait "h1:has-text('Ontology')" --out $W/shots
```

Routes are `#/` (repositories), `#/snapshots/<id>`, `#/impact`, `#/query`, `#/ontology`, `#/runs` and
`#/runs/<id>`. Open the PNGs and look at them; the driver passing doesn't prove the layout is right.

## Direct invocation (no server)

Engine, impact and tool changes can be exercised on the in-memory shop graph, with no database at all:

```bash
./venv/bin/python -c "
from tests.engine.helpers import shop_graph
from tracegraph.engine import Evaluator, ir
g = shop_graph()
r = Evaluator(g).evaluate(ir.Dsl(text='?- untested_writer(E).', rule_pack='core'))
print([g.nodes[x['node']].key for x in r.rows])"
```

The CLI against the database: `./venv/bin/tg query 1 examples/endpoints_writing_orders.yaml` and
`./venv/bin/tg impact 1 examples/make_discount_nullable.yaml`. Add `TG_OTEL_EXPORTER=console` to print trace spans.

## Test

The tests use their own database, `tracegraph_test`, defaulting to port 55432. On the cluster above:

```bash
/usr/lib/postgresql/17/bin/createdb -h localhost -p 55433 -U tg tracegraph_test
TG_TEST_DATABASE_URL=postgresql+psycopg://tg@localhost:55433/tracegraph_test ./venv/bin/python -m pytest tests -q
```

## Stop

```bash
pkill -f "[t]g serve --port 8766"; pkill -f "[t]g worker"
/usr/lib/postgresql/17/bin/pg_ctl -D $W/pgdata stop -m fast
```

## Run (human path)

Start the stack as above, open `http://localhost:8766/ui/` and paste `TG_API_KEY` into the "API key" box.
Without a key the page shows an error; that's expected.

## Gotchas

- **`.env` at the repo root holds real Gemini API keys** and `TG_DATABASE_URL` for port 5432, where nothing is
  listening on this machine. pydantic-settings reads it automatically and exported `TG_*` variables override it.
  Always export `TG_DATABASE_URL`, and never print or commit `.env`. The tests ignore `.env` (`_env_file=None`).
- **Pass `-E UTF8 --locale=C.UTF-8` to initdb.** Without `LANG` in the environment (a minimal shell, `env -i`,
  CI), initdb creates a `SQL_ASCII` cluster. psycopg then returns bytes, and the server fails on its first query
  with `TypeError: cannot use a string pattern on a bytes-like object` (in `_get_server_version_info`).
- **The first `playwright install chromium` downloads about 191 MiB** (Chrome for Testing plus the headless
  shell). A chunk can fail with `Error: read ETIMEDOUT`; the installer retries on its own, so let it finish.
  With `PLAYWRIGHT_BROWSERS_PATH` pointed at an existing download, it's a no-op.
- **Start Postgres with `-k ''`** (TCP only). Under a deep scratch directory the default unix socket path is
  longer than the 107-byte limit and the server won't start.
- **The repository picker on Impact and Query defaults to the first repository.** If you index more than one,
  pass `--repo` to the driver. With the wrong repo, examples come back empty, and the Diff example returns 422
  ("No Column with key 'orders.total'").
- **The browser console shows a 401 before the key is entered.** The driver ignores 401s and nothing else.
- **Playwright warns "your OS is not officially supported"** on Ubuntu 25.10 and downloads the ubuntu24.04
  build. The headless shell runs with `--no-sandbox`, and no extra apt packages were needed here.
- **Snapshot ids and repository ids are separate counters.** On a fresh database both are 1, but after a few
  re-indexes they drift apart.
- **`pkill -f "tg serve ..."` kills the shell running it** (exit code 144), because that shell's own command line
  contains the pattern. Write `[t]g serve` as in Stop: it still matches the server but not itself.
- **`tg serve` binds 127.0.0.1:8000 by default.** The commands here use 8766 so they don't collide with
  another instance.

## Troubleshooting

- `pg_ctl: could not start server` with a socket path error in `pg.log` → add `-o "-k ''"` (above).
- `TypeError: cannot use a string pattern on a bytes-like object` from SQLAlchemy at startup → the cluster is
  `SQL_ASCII`. Recreate it with `-E UTF8 --locale=C.UTF-8`.
- Tests fail to connect on 55432 → set `TG_TEST_DATABASE_URL` and create `tracegraph_test` on your cluster.
