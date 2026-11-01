from functools import lru_cache

from tracegraph.tools.graph_tools import GRAPH_TOOLS
from tracegraph.tools.impact_tools import IMPACT_TOOLS
from tracegraph.tools.reasoning_tools import REASONING_TOOLS
from tracegraph.tools.registry import ToolCallResult, ToolContext, ToolOutput, ToolRegistry, ToolSpec
from tracegraph.tools.workspace_tools import WORKSPACE_TOOLS


@lru_cache(maxsize=1)
def get_tool_registry() -> ToolRegistry:
    """
    #Feature: Tool registry
    #Scenario: Process-wide registry with every tool registered once
    #Complexity: Time O(t) once, then O(1)
    """
    registry = ToolRegistry()
    for spec in [*GRAPH_TOOLS, *REASONING_TOOLS, *IMPACT_TOOLS, *WORKSPACE_TOOLS]:
        registry.register(spec)
    return registry


__all__ = ["ToolCallResult", "ToolContext", "ToolOutput", "ToolRegistry", "ToolSpec", "get_tool_registry"]
