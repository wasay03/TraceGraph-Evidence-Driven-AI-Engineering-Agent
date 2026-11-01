from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any


@dataclass(slots=True)
class LlmTurn:
    """
    #Feature: Agent LLM boundary
    #Scenario: One model response: serialised content blocks (appended back verbatim), stop reason and usage
    #Complexity: Time O(1) - constant
    """

    content: list[dict[str, Any]]
    stop_reason: str
    input_tokens: int = 0
    output_tokens: int = 0
    model: str = ""
    refusal: str | None = None
    tool_calls: list[dict[str, Any]] = field(default_factory=list)


class ILlmClient(ABC):
    """
    #Feature: Agent LLM boundary
    #Scenario: Contract for one model turn; the state machine owns the loop (PRD D13)
    #Complexity: Time O(1) per call excluding the model
    """

    @abstractmethod
    async def turn(self, system: str, messages: list[dict[str, Any]], tools: list[dict[str, Any]]) -> LlmTurn:
        """
        #Feature: Agent LLM boundary
        #Scenario: Send the conversation and tool definitions, return the next assistant turn
        #Complexity: Time O(1) excluding the model
        """
