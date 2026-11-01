import asyncio
import logging
import socket
import uuid

from tracegraph.config import Settings
from tracegraph.containers import RepositoryContainer, ServiceContainer
from tracegraph.core import Database

logger = logging.getLogger(__name__)


class IndexWorker:
    """
    #Feature: Background indexing (PRD 13.1)
    #Scenario: Poll the job table; each job runs in its own transaction, failures are recorded in a second one
    #Complexity: Time O(1) per poll excluding job work
    """

    def __init__(self, database: Database, settings: Settings, worker_id: str | None = None) -> None:
        """
        #Feature: Background indexing
        #Scenario: Bind to the database and settings
        #Complexity: Time O(1) - constant

        Raises:
            ValueError: When database or settings is None.
        """
        if database is None or settings is None:
            raise ValueError("[IndexWorker.__init__] 'database' and 'settings' are required.")
        self._db = database
        self._settings = settings
        self.worker_id = worker_id or f"{socket.gethostname()}-{uuid.uuid4().hex[:8]}"

    def _services(self, session) -> ServiceContainer:
        """
        #Feature: Background indexing
        #Scenario: Fresh containers per transaction
        #Complexity: Time O(1) - constant
        """
        return ServiceContainer(RepositoryContainer(session), self._settings)

    async def run_once(self) -> bool:
        """
        #Feature: Background indexing
        #Scenario: Claim one job and execute it; returns False when the queue is empty
        #Complexity: Time O(N * r) - extraction cost of the job
        """
        async with self._db.transaction() as session:
            job = await self._services(session).indexing.claim(self.worker_id)
        if job is None:
            return False
        log_ctx = {"job_id": job["id"], "repo_id": job["repo_id"], "worker": self.worker_id}
        try:
            async with self._db.transaction() as session:
                await self._services(session).indexing.run(job)
        except Exception as exc:
            logger.exception("Index job failed", extra=log_ctx)
            async with self._db.transaction() as session:
                await self._services(session).indexing.fail(job, f"{type(exc).__name__}: {exc}")
        return True

    async def run_forever(self) -> None:
        """
        #Feature: Background indexing
        #Scenario: Drain the queue, then sleep for the poll interval
        #Complexity: Time O(1) per idle poll
        """
        logger.info("Index worker started", extra={"worker": self.worker_id})
        while True:
            if not await self.run_once():
                await asyncio.sleep(self._settings.worker_poll_seconds)
