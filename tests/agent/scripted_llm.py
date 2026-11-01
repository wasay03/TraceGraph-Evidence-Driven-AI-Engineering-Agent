import itertools
import re
from collections.abc import Callable
from typing import Any

from tracegraph.interfaces.llm import ILlmClient, LlmTurn

HANDLE = re.compile(r"handle=(ans_[0-9a-f]{32})")
PATCH = re.compile(r"applied (p[0-9a-f]{8})")
Step = Callable[[list[dict[str, Any]]], list[tuple[str, dict[str, Any]]]]


def tool_results(messages: list[dict[str, Any]]) -> list[str]:
    """Texts of every tool_result in the conversation so far."""
    return [b["content"] for m in messages if m["role"] == "user" and isinstance(m["content"], list)
            for b in m["content"] if b.get("type") == "tool_result"]


def handles(messages: list[dict[str, Any]]) -> list[str]:
    return [h for text in tool_results(messages) for h in HANDLE.findall(text)]


def issued_handles(messages: list[dict[str, Any]]) -> list[str]:
    """Handles listed in the phase's compiled context (report phase)."""
    opening = messages[0]["content"]
    return opening.split("## Handles issued in this run\n")[1].split("\n")[0].split(", ")


def patches(messages: list[dict[str, Any]]) -> list[str]:
    return [p for text in tool_results(messages) for p in PATCH.findall(text)]


class ScriptedLlm(ILlmClient):
    """Replays scripted tool calls per phase; each step sees the conversation so far."""

    def __init__(self, script: dict[str, list[Step]]) -> None:
        self._script = {phase: iter(steps) for phase, steps in script.items()}
        self._ids = itertools.count()
        self.systems: list[str] = []
        self.results: list[str] = []

    async def turn(self, system: str, messages: list[dict[str, Any]], tools: list[dict[str, Any]]) -> LlmTurn:
        self.systems.append(system)
        phase = re.search(r"Phase: (\w+)\.", system).group(1)
        offered = {t["name"] for t in tools}
        self.results.extend(tool_results(messages[-1:]))
        calls = next(self._script[phase])(messages)
        content = [{"type": "tool_use", "id": f"toolu_{next(self._ids)}", "name": name, "input": args}
                   for name, args in calls]
        assert all(name in offered for name, _ in calls), (phase, [n for n, _ in calls], sorted(offered))
        return LlmTurn(content, "tool_use", 100, 50, "scripted", None, content)
