from abc import ABC, abstractmethod
from typing import Any


class IOverlayRepository(ABC):
    """
    #Feature: What-if overlays
    #Scenario: Contract for persisting hypothesized change sets
    #Complexity: Time O(1) per call
    """

    @abstractmethod
    async def create(self, repo_id: int, base_seq: int, change_spec: dict[str, Any], ops: list[dict[str, Any]]) -> int:
        """
        #Feature: What-if overlays
        #Scenario: Store an overlay and its ordered ops; returns the overlay id
        #Complexity: Time O(o) - linear in ops
        """

    @abstractmethod
    async def get(self, overlay_id: int) -> dict[str, Any]:
        """
        #Feature: What-if overlays
        #Scenario: Overlay with its ops (TG404 when missing)
        #Complexity: Time O(o) - linear in ops
        """
