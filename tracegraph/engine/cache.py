import threading
from collections import OrderedDict

from tracegraph.constants.engine import SNAPSHOT_CACHE_SIZE
from tracegraph.engine.graph import GraphSnapshot


class SnapshotCache:
    """
    #Feature: In-memory snapshot cache (PRD 6)
    #Scenario: LRU of loaded snapshots keyed by (repo_id, seq); snapshots are immutable so sharing is safe
    #Complexity: Time O(1) per get/put
    """

    def __init__(self, capacity: int = SNAPSHOT_CACHE_SIZE) -> None:
        """
        #Feature: In-memory snapshot cache
        #Scenario: Create an empty cache
        #Complexity: Time O(1) - constant

        Raises:
            ValueError: When capacity is not positive.
        """
        if capacity < 1:
            raise ValueError("[SnapshotCache.__init__] 'capacity' must be >= 1.")
        self._capacity = capacity
        self._items: OrderedDict[tuple[int, int], GraphSnapshot] = OrderedDict()
        self._lock = threading.Lock()
        self.hits = 0
        self.misses = 0

    def get(self, repo_id: int, seq: int) -> GraphSnapshot | None:
        """
        #Feature: In-memory snapshot cache
        #Scenario: Cached snapshot or None; refreshes recency
        #Complexity: Time O(1) - constant
        """
        with self._lock:
            graph = self._items.get((repo_id, seq))
            if graph is None:
                self.misses += 1
                return None
            self._items.move_to_end((repo_id, seq))
            self.hits += 1
            return graph

    def put(self, graph: GraphSnapshot) -> None:
        """
        #Feature: In-memory snapshot cache
        #Scenario: Insert and evict the least recently used entry beyond capacity
        #Complexity: Time O(1) - constant

        Raises:
            ValueError: When graph is None.
        """
        if graph is None:
            raise ValueError("[SnapshotCache.put] 'graph' is required.")
        with self._lock:
            self._items[(graph.repo_id, graph.seq)] = graph
            self._items.move_to_end((graph.repo_id, graph.seq))
            while len(self._items) > self._capacity:
                self._items.popitem(last=False)
