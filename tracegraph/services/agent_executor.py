import asyncio
import logging
from collections.abc import AsyncIterator, Callable
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any

from tracegraph.agent.fsm import AgentRunner, RunEnvironment
from tracegraph.agent.phase_runner import PhaseRunner
from tracegraph.agent.state import RunState
from tracegraph.config import Settings
from tracegraph.constants import agent as a
from tracegraph.containers import RepositoryContainer, ServiceContainer
from tracegraph.core import Database
from tracegraph.engine import SnapshotCache
from tracegraph.interfaces.llm import ILlmClient
from tracegraph.sandbox.run_sandbox import SandboxWorkspace
from tracegraph.tools import get_tool_registry

logger = logging.getLogger(__name__)

# Failed and exhausted runs keep their sandbox so a retry can resume them.
_CLEANUP = frozenset({a.STATUS_COMPLETED, a.STATUS_REJECTED})


class _DbRunStore:
    """
    #Feature: Agent execution
    #Scenario: RunStore over AgentService, one transaction per write, tracking the row version
    #Complexity: Time O(1) per call
    """

    def __init__(self, services: Callable[[], Any], run_id: int, version: int) -> None:
        """
        #Feature: Agent execution
        #Scenario: Bind to a run at a known version
        #Complexity: Time O(1) - constant
        """
        self._services, self._run_id, self.version = services, run_id, version

    async def save(self, status: str, phase: str, state: RunState) -> None:
        """
        #Feature: Agent execution
        #Scenario: Versioned transition
        #Complexity: Time O(s) - state size
        """
        async with self._services() as services:
            self.version = await services.agent.save(self._run_id, self.version, status, phase,
                                                     state.model_dump(mode="json"))

    async def event(self, kind: str, phase: str, payload: dict[str, Any]) -> None:
        """
        #Feature: Agent execution
        #Scenario: Audit event
        #Complexity: Time O(1) - constant
        """
        async with self._services() as services:
            await services.agent.event(self._run_id, kind, phase, payload)


class AgentExecutor:
    """
    #Feature: Agent execution
    #Scenario: Composition root for runs: services per transaction, sandbox, LLM client, state machine
    #Complexity: Time per run
    """

    def __init__(self, database: Database, settings: Settings, cache: SnapshotCache,
                 llm_factory: Callable[[], ILlmClient]) -> None:
        """
        #Feature: Agent execution
        #Scenario: Constructor injection; the LLM client is built on first use (credentials resolve then)
        #Complexity: Time O(1) - constant

        Raises:
            ValueError: When a dependency is None.
        """
        if database is None or settings is None or cache is None or llm_factory is None:
            raise ValueError("[AgentExecutor.__init__] all dependencies are required.")
        self._db, self._settings, self._cache, self._llm_factory = database, settings, cache, llm_factory
        self._llm: ILlmClient | None = None
        self._locks: dict[int, asyncio.Lock] = {}

    @asynccontextmanager
    async def services(self) -> AsyncIterator[ServiceContainer]:
        """
        #Feature: Agent execution
        #Scenario: One transaction with fresh containers
        #Complexity: Time O(1) - constant
        """
        async with self._db.transaction() as session:
            yield ServiceContainer(RepositoryContainer(session), self._settings, self._cache)

    async def _environment(self, run: dict[str, Any], state: RunState) -> RunEnvironment:
        """
        #Feature: Agent execution
        #Scenario: Snapshot graph, repository location and the run's sandbox (created on first execution)
        #Complexity: Time O(n + e) on a cache miss plus worktree creation
        """
        async with self.services() as services:
            graph = await services.query.load_graph(run["repo_id"], run["snapshot_id"])
            repo = await services.repos.get(run["repo_id"])
            path = services.workspace.local_path(repo.url)
        state.snapshot_id, state.snapshot_seq, state.commit = run["snapshot_id"], graph.seq, graph.commit
        if state.worktree is None or not Path(state.worktree).is_dir():
            sandbox = await asyncio.to_thread(SandboxWorkspace.create, path, Path(self._settings.sandbox_dir),
                                              graph.commit, run["id"], self._settings.sandbox_python)
            state.worktree = str(sandbox.root)
            for patch in state.patches:
                await asyncio.to_thread(sandbox.apply_patch, patch["diff"])
        else:
            sandbox = SandboxWorkspace(path, Path(state.worktree), self._settings.sandbox_python)
        return RunEnvironment(run["id"], run["mode"], run["config"], run["request"], graph, repo.url, sandbox)

    async def execute(self, run_id: int) -> str:
        """
        #Feature: Agent execution
        #Scenario: Advance a queued run until it completes or pauses; one executor per run at a time
        #Complexity: Time per run
        """
        lock = self._locks.setdefault(run_id, asyncio.Lock())
        async with lock:
            async with self.services() as services:
                run = await services.agent.load(run_id)
            if run["status"] not in a.RESUMABLE_STATUSES:
                return run["status"]
            state = RunState.model_validate(run["state"])
            if not run["state"].get("budget"):
                state.budget.max_llm_calls = self._settings.llm_max_calls_per_run
            env = await self._environment(run, state)
            store = _DbRunStore(self.services, run_id, run["version"])
            self._llm = self._llm or self._llm_factory()
            phases = PhaseRunner(self._llm, get_tool_registry(), self.services, store.event)
            status = await AgentRunner(env, phases, self.services, store).advance(run["phase"], state)
            if status in _CLEANUP and run["mode"] == a.MODE_BENCHMARK:
                await asyncio.to_thread(env.sandbox.cleanup)
            logger.info("Run paused or finished", extra={"run_id": run_id, "status": status})
            return status

