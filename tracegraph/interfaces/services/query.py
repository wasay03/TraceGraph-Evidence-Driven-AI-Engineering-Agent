from abc import ABC, abstractmethod

from tracegraph.engine import GraphSnapshot
from tracegraph.engine.answer import Answer
from tracegraph.schemas.query import QueryRequest


class IQueryService(ABC):
    """
    #Feature: Reasoning engine service
    #Scenario: Contract for running IR queries and retrieving stored answers
    #Complexity: Time per query as documented on the IR
    """

    @abstractmethod
    async def load_graph(self, repo_id: int, snapshot_id: int | None) -> GraphSnapshot:
        """
        #Feature: Reasoning engine service
        #Scenario: Cached in-memory snapshot of a ready snapshot (latest ready when snapshot_id is None)
        #Complexity: Time O(n + e) on cache miss
        """

    @abstractmethod
    async def run(self, request: QueryRequest) -> Answer:
        """
        #Feature: Reasoning engine service
        #Scenario: Evaluate, attach evidence, persist and return the Answer with its handle
        #Complexity: Time per query
        """

    @abstractmethod
    async def answer_for(self, graph: GraphSnapshot, query: object, query_ir: dict, max_rows: int) -> Answer:
        """
        #Feature: Reasoning engine service
        #Scenario: Evaluate a query on a given (possibly overlaid) graph and persist the Answer
        #Complexity: Time per query
        """

    @abstractmethod
    async def get_answer(self, handle: str) -> Answer:
        """
        #Feature: Reasoning engine service
        #Scenario: Full stored answer with derivations
        #Complexity: Time O(1) - unique index lookup
        """
