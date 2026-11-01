import asyncio
import json
from collections.abc import Awaitable, Callable
from pathlib import Path
from typing import Any

import typer
import uvicorn
import yaml

from tracegraph.config import get_settings
from tracegraph.containers import RepositoryContainer, ServiceContainer
from tracegraph.core import Database, configure_logging
from tracegraph.impact.report import ImpactReport
from tracegraph.schemas.impact import ImpactRequest
from tracegraph.schemas.query import QueryRequest
from tracegraph.schemas.repos import RepoCreateRequest
from tracegraph.schemas.snapshots import SnapshotCreateRequest
from tracegraph.workers import IndexWorker

app = typer.Typer(help="TraceGraph command line", no_args_is_help=True)


@app.command()
def serve(host: str = "127.0.0.1", port: int = 8000) -> None:
    """
    #Feature: CLI
    #Scenario: Run the HTTP API
    #Complexity: Time O(1) - starts a server
    """
    uvicorn.run("tracegraph.main:create_app", factory=True, host=host, port=port)


@app.command()
def worker() -> None:
    """
    #Feature: CLI
    #Scenario: Run the background index worker until interrupted
    #Complexity: Time O(1) per idle poll
    """
    settings = get_settings()
    configure_logging(settings.log_level)
    asyncio.run(IndexWorker(Database(settings), settings).run_forever())


async def _index(path: Path, ref: str, incremental: bool) -> dict:
    """
    #Feature: CLI
    #Scenario: Register (idempotently), queue a snapshot and execute it inline
    #Complexity: Time O(N * r) - extraction cost
    """
    settings = get_settings()
    database = Database(settings)
    try:
        async with database.transaction() as session:
            services = ServiceContainer(RepositoryContainer(session), settings)
            repo = await services.repos.ensure(RepoCreateRequest(url=str(path.resolve())))
            kind = "incremental" if incremental else "full"
            queued = await services.snapshots.request_index(repo.id, SnapshotCreateRequest(ref=ref, kind=kind))
        await IndexWorker(database, settings).run_once()
        async with database.transaction() as session:
            services = ServiceContainer(RepositoryContainer(session), settings)
            return (await services.snapshots.get(queued.snapshot.id)).model_dump(mode="json")
    finally:
        await database.dispose()


@app.command()
def index(
    path: Path = typer.Argument(..., exists=True, file_okay=False),
    ref: str = typer.Option("HEAD", help="Git ref, or WORKTREE for uncommitted files"),
    incremental: bool = typer.Option(False, help="Re-commit only files changed since the last ready snapshot"),
) -> None:
    """
    #Feature: CLI
    #Scenario: tg index <repo> [--ref] [--incremental]
    #Complexity: Time O(N * r) - extraction cost
    """
    snapshot = asyncio.run(_index(path, ref, incremental))
    summary = {k: snapshot[k] for k in ("id", "seq", "commit_sha", "status", "error")}
    typer.echo(json.dumps({**summary, "stats": snapshot["stats"]}, indent=2))
    raise typer.Exit(code=0 if snapshot["status"] == "ready" else 1)


async def _with_services(action: Callable[[ServiceContainer], Awaitable[Any]]) -> Any:
    """
    #Feature: CLI
    #Scenario: Run one action inside a transaction with fresh containers (composition root for the CLI)
    #Complexity: Time O(1) plus the action
    """
    settings = get_settings()
    database = Database(settings)
    try:
        async with database.transaction() as session:
            return await action(ServiceContainer(RepositoryContainer(session), settings))
    finally:
        await database.dispose()


def _load(path: Path) -> Any:
    """
    #Feature: CLI
    #Scenario: Parse a YAML or JSON file
    #Complexity: Time O(s) - file size
    """
    return yaml.safe_load(path.read_text(encoding="utf-8"))


def _render_impact(report: ImpactReport) -> str:
    """
    #Feature: CLI
    #Scenario: Human-readable impact report grouped by class
    #Complexity: Time O(f) - findings
    """
    lines = [f"Impact on {report.snapshot.commit[:12]} (seq {report.snapshot.seq}) - handle {report.handle}",
             "Summary: " + ", ".join(f"{k}={v}" for k, v in report.summary.items()), ""]
    for f in report.findings:
        where = f"{f.evidence[-1].file}:{f.evidence[-1].lines[0]}" if f.evidence else (f.node.file or "")
        lines.append(f"  {f.cls:8} {f.node.type:10} {f.node.key:55} {f.reason:32} score={f.score:<6} {where}")
    lines += ["", "Obligations:"] + [f"  - {o.kind}: {o.target.key} ({o.detail})" for o in report.obligations]
    lines += ["", "Tests to run:"] + [f"  - {t.node.key} (score {t.score})" for t in report.tests]
    lines += ["", "Invariant changes:"] + [f"  - [{i.status}] {i.invariant} {i.message}" for i in report.invariants]
    if report.coverage_gaps:
        lines += ["", "Coverage gaps:"] + [f"  - {g['node']}: {g['kind']}" for g in report.coverage_gaps]
    return "\n".join(lines)


@app.command()
def query(repo_id: int, ir_file: Path = typer.Argument(..., exists=True, dir_okay=False)) -> None:
    """
    #Feature: CLI
    #Scenario: tg query <repo_id> <ir.yaml|json> - run typed IR, print the Answer JSON
    #Complexity: Time per query
    """
    request = QueryRequest(repo_id=repo_id, query=_load(ir_file))
    answer = asyncio.run(_with_services(lambda services: services.query.run(request)))
    typer.echo(answer.model_dump_json(indent=2))


@app.command()
def impact(repo_id: int, spec_file: Path = typer.Argument(..., exists=True, dir_okay=False),
           as_json: bool = typer.Option(False, "--json", help="Print the full report as JSON")) -> None:
    """
    #Feature: CLI
    #Scenario: tg impact <repo_id> <changespec.yaml> - ChangeSpecs (a list or {changes: [...]}) -> impact report
    #Complexity: Time per analysis
    """
    data = _load(spec_file)
    request = ImpactRequest(repo_id=repo_id, changes=data["changes"] if isinstance(data, dict) else data)
    report = asyncio.run(_with_services(lambda services: services.impact.analyze(request)))
    typer.echo(report.model_dump_json(indent=2) if as_json else _render_impact(report))


if __name__ == "__main__":
    app()
