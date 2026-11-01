import asyncio
import json
from pathlib import Path

import typer
import uvicorn

from tracegraph.config import get_settings
from tracegraph.containers import RepositoryContainer, ServiceContainer
from tracegraph.core import Database, configure_logging
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


if __name__ == "__main__":
    app()
