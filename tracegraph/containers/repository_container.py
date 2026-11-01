from sqlalchemy.ext.asyncio import AsyncSession

from tracegraph.interfaces.repositories import (
    IAnswerRepository,
    IGraphRepository,
    IHealthRepository,
    IIndexJobRepository,
    IOntologyRepository,
    IRepoRepository,
    ISnapshotRepository,
)
from tracegraph.repositories import (
    AnswerRepository,
    GraphRepository,
    HealthRepository,
    IndexJobRepository,
    OntologyRepository,
    RepoRepository,
    SnapshotRepository,
)


class RepositoryContainer:
    """
    #Feature: Dependency injection
    #Scenario: Lazily build repositories bound to one database session
    #Complexity: Time O(1) - constant per property access

    One container per request or background job.
    """

    def __init__(self, session: AsyncSession) -> None:
        """
        #Feature: Dependency injection
        #Scenario: Bind the container to a session
        #Complexity: Time O(1) - constant

        Args:
            session: Active AsyncSession shared by all repositories in this container.

        Raises:
            ValueError: When session is None.
        """
        if session is None:
            raise ValueError("[RepositoryContainer.__init__] 'session' is required and must not be None.")
        self._session = session
        self._health: IHealthRepository | None = None
        self._ontology: IOntologyRepository | None = None
        self._repos: IRepoRepository | None = None
        self._snapshots: ISnapshotRepository | None = None
        self._jobs: IIndexJobRepository | None = None
        self._graph: IGraphRepository | None = None
        self._answers: IAnswerRepository | None = None

    @property
    def health(self) -> IHealthRepository:
        """
        #Feature: Dependency injection
        #Scenario: Lazy health repository
        #Complexity: Time O(1) - constant
        """
        if self._health is None:
            self._health = HealthRepository(self._session)
        return self._health

    @property
    def ontology(self) -> IOntologyRepository:
        """
        #Feature: Dependency injection
        #Scenario: Lazy ontology catalog repository
        #Complexity: Time O(1) - constant
        """
        if self._ontology is None:
            self._ontology = OntologyRepository(self._session)
        return self._ontology

    @property
    def repos(self) -> IRepoRepository:
        """
        #Feature: Dependency injection
        #Scenario: Lazy repository-registry repository
        #Complexity: Time O(1) - constant
        """
        if self._repos is None:
            self._repos = RepoRepository(self._session)
        return self._repos

    @property
    def snapshots(self) -> ISnapshotRepository:
        """
        #Feature: Dependency injection
        #Scenario: Lazy snapshot repository
        #Complexity: Time O(1) - constant
        """
        if self._snapshots is None:
            self._snapshots = SnapshotRepository(self._session)
        return self._snapshots

    @property
    def jobs(self) -> IIndexJobRepository:
        """
        #Feature: Dependency injection
        #Scenario: Lazy index job repository
        #Complexity: Time O(1) - constant
        """
        if self._jobs is None:
            self._jobs = IndexJobRepository(self._session)
        return self._jobs

    @property
    def graph(self) -> IGraphRepository:
        """
        #Feature: Dependency injection
        #Scenario: Lazy graph store repository
        #Complexity: Time O(1) - constant
        """
        if self._graph is None:
            self._graph = GraphRepository(self._session)
        return self._graph

    @property
    def answers(self) -> IAnswerRepository:
        """
        #Feature: Dependency injection
        #Scenario: Lazy answer store repository
        #Complexity: Time O(1) - constant
        """
        if self._answers is None:
            self._answers = AnswerRepository(self._session)
        return self._answers
