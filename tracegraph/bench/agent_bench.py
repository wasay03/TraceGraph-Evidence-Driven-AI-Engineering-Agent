import asyncio
import logging
import shutil
import subprocess
import tempfile
from collections.abc import Callable
from pathlib import Path
from typing import Any

from tracegraph.bench.metrics import bootstrap_ci, prf, wilcoxon_signed_rank
from tracegraph.bench.tasks import Suite, Task
from tracegraph.config import Settings
from tracegraph.constants.agent import MODE_BENCHMARK, STATUS_COMPLETED
from tracegraph.core import Database
from tracegraph.engine import SnapshotCache
from tracegraph.errors import AppError
from tracegraph.interfaces.llm import ILlmClient
from tracegraph.sandbox.run_sandbox import SandboxWorkspace
from tracegraph.schemas.repos import RepoCreateRequest
from tracegraph.schemas.runs import RunCreateRequest
from tracegraph.schemas.snapshots import SnapshotCreateRequest
from tracegraph.services.agent_executor import AgentExecutor
from tracegraph.workers import IndexWorker

logger = logging.getLogger(__name__)


def _fresh_repo(source: Path, workdir: Path) -> Path:
    """
    #Feature: Agent benchmark
    #Scenario: Copy the task repository into a new git repository so every run starts from the same commit
    #Complexity: Time O(f) - files copied
    """
    path = workdir / "repo"
    shutil.copytree(source, path, ignore=shutil.ignore_patterns("__pycache__", ".git"))
    for args in (["init", "-q", "-b", "main"], ["add", "-A"],
                 ["-c", "user.email=bench@tracegraph", "-c", "user.name=bench", "commit", "-q", "-m", "base"]):
        subprocess.run(["git", "-C", str(path), *args], check=True, capture_output=True)
    return path


def _hidden_tests(base: Path, patches: list[dict[str, Any]], tests: list[str], workdir: Path, python: str | None
                  ) -> bool | None:
    """
    #Feature: Agent benchmark (PRD 11.2 rung 9)
    #Scenario: Replay the run's patches on a pristine copy and run the hidden tests the agent never saw
    #Complexity: Time O(test runtime)
    """
    if not tests:
        return None
    copy = _fresh_repo(base, workdir / "hidden")
    sandbox = SandboxWorkspace(copy, copy, python)
    try:
        for patch in patches:
            sandbox.apply_patch(patch["diff"])
    except AppError:  # a patch set that no longer applies fails the hidden tests by definition
        return False
    return bool(sandbox.run_tests(tests)["ok"])


async def _index_until_done(database: Database, settings: Settings, executor: AgentExecutor, snapshot_id: int,
                            max_jobs: int = 50) -> None:
    """
    #Feature: Agent benchmark
    #Scenario: Drain the queue (oldest first) until this run's snapshot is ready
    #Complexity: Time O(jobs * extraction)

    Raises:
        RuntimeError: When the snapshot fails or never becomes ready.
    """
    worker = IndexWorker(database, settings, "bench")
    for _ in range(max_jobs):
        async with executor.services() as services:
            status = (await services.snapshots.get(snapshot_id)).status
        if status == "ready":
            return
        if status == "failed" or not await worker.run_once():
            break
    raise RuntimeError(f"[agent_bench] snapshot {snapshot_id} did not become ready (status {status}).")


def _score(task: Task, status: str, state: dict[str, Any], hidden: bool | None) -> dict[str, Any]:
    """
    #Feature: Agent benchmark (PRD 12.1 "Agent" layer)
    #Scenario: Success, regression signal, scope precision/recall over files, impact P/R when simulated, cost
    #Complexity: Time O(f) - findings and files
    """
    verification = state.get("verification") or {}
    touched = {f for p in state.get("patches", []) for f in p["files"]}
    scope = prf(touched, set(task.gold.files))
    impact = state.get("impact") or {}
    predicted = {f["key"] for f in impact.get("findings", []) if f["cls"] != "GUARDED"}
    budget = state.get("budget", {})
    return {"status": status, "success": status == STATUS_COMPLETED and bool(verification.get("passed")) and hidden
            is not False, "hidden_tests_passed": hidden, "scope_precision": scope["precision"],
            "scope_recall": scope["recall"], "impact_recall": prf(predicted, task.gold.affected)["recall"] if impact
            else None, "tool_calls": budget.get("tool_calls", 0), "output_tokens": budget.get("output_tokens", 0),
            "input_tokens": budget.get("input_tokens", 0), "error": state.get("error")}


async def _one_run(task: Task, suite: Suite, config: str, settings: Settings,
                   llm_factory: Callable[[], ILlmClient]) -> dict[str, Any]:
    """
    #Feature: Agent benchmark
    #Scenario: Fresh repo -> register -> index -> agent run in benchmark mode -> hidden tests -> score
    #Complexity: Time per run
    """
    source = (suite.base_dir / task.repo).resolve()
    with tempfile.TemporaryDirectory(prefix=f"tg-bench-{task.id}-") as tmp:
        workdir = Path(tmp)
        repo_path = await asyncio.to_thread(_fresh_repo, source, workdir)
        run_settings = settings.model_copy(update={"sandbox_dir": str(workdir / "sandboxes")})
        database = Database(run_settings)
        try:
            executor = AgentExecutor(database, run_settings, SnapshotCache(), llm_factory)
            async with executor.services() as services:
                repo = await services.repos.ensure(RepoCreateRequest(url=str(repo_path)))
                queued = await services.snapshots.request_index(repo.id, SnapshotCreateRequest())
            await _index_until_done(database, run_settings, executor, queued.snapshot.id)
            async with executor.services() as services:
                run = await services.agent.start(RunCreateRequest(repo_id=repo.id, request=task.request,
                                                                  mode=MODE_BENCHMARK, config=config))
            status = await executor.execute(run.id)
            async with executor.services() as services:
                state = (await services.agent.get(run.id)).state
        finally:
            await database.dispose()
        hidden = await asyncio.to_thread(_hidden_tests, source, state.get("patches", []), task.hidden_tests, workdir,
                                         settings.sandbox_python)
    return {"task": task.id, "config": config, "run_id": run.id, **_score(task, status, state, hidden)}


def _aggregate(rows: list[dict[str, Any]], configs: list[str]) -> dict[str, Any]:
    """
    #Feature: Agent benchmark (PRD 12.4)
    #Scenario: Per-config means with 95% bootstrap intervals; paired Wilcoxon between the first and last config
    #Complexity: Time O(bootstrap iterations * rows)
    """
    summary: dict[str, Any] = {}
    for config in configs:
        mine = [r for r in rows if r["config"] == config]
        summary[config] = {m: bootstrap_ci([float(r[m] or 0) for r in mine])
                           for m in ("success", "scope_precision", "scope_recall", "tool_calls", "output_tokens")}
    if len(configs) >= 2:
        # rows are appended task by task and run by run, so per-config lists are already paired
        first, last = configs[0], configs[-1]
        base = [float(r["success"]) for r in rows if r["config"] == first]
        full = [float(r["success"]) for r in rows if r["config"] == last]
        summary[f"wilcoxon_success_{first}_vs_{last}"] = wilcoxon_signed_rank(base, full)
    return summary


async def run_agent_benchmark(suite: Suite, configs: list[str], runs: int, settings: Settings,
                              llm_factory: Callable[[], ILlmClient], task_ids: list[str] | None = None) -> dict[str, Any]:
    """
    #Feature: Agent benchmark (PRD 12.3-12.4)
    #Scenario: runs x configs x tasks, each on a fresh repository copy; same model, loop and budgets for all configs
    #Complexity: Time O(tasks * configs * runs * run time)

    Raises:
        ValueError: When configs or runs are invalid.
    """
    if not configs or runs < 1:
        raise ValueError("[run_agent_benchmark] at least one config and one run are required.")
    tasks = [t for t in suite.tasks if task_ids is None or t.id in task_ids]
    rows = []
    for task in tasks:
        for config in configs:
            for _ in range(runs):
                rows.append(await _one_run(task, suite, config, settings, llm_factory))
                logger.info("Benchmark run done", extra={"task": task.id, "config": config, **{
                    k: rows[-1][k] for k in ("status", "success", "tool_calls")}})
    return {"suite": suite.name, "frozen": suite.frozen, "configs": configs, "runs": runs, "rows": rows,
            "summary": _aggregate(rows, configs)}
