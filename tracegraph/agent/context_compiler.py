import json

from tracegraph.agent.state import RunState
from tracegraph.constants import agent as a


def _section(title: str, body: str | None) -> str:
    """
    #Feature: Context compilation (PRD 10.4)
    #Scenario: One titled block, omitted when empty
    #Complexity: Time O(b) - body size
    """
    return f"## {title}\n{body}\n" if body else ""


def _impact(state: RunState) -> str | None:
    """
    #Feature: Context compilation
    #Scenario: Impact findings, obligations and tests as compact lines
    #Complexity: Time O(f) - findings
    """
    impact = state.impact
    if not impact:
        return None
    lines = [f"report handle {impact['handle']}, changes {json.dumps(impact['changes'])}"]
    lines += [f"- {f['cls']} {f['type']} {f['key']} ({f['reason']}) in {f['file']}" for f in impact["findings"]]
    lines += [f"- obligation {o['kind']}: {o['target']} - {o['detail']}" for o in impact["obligations"]]
    lines += [f"- test {t}" for t in impact["tests"]]
    lines += [f"- invariant [{i['status']}] {i['id']}: {i['message']}" for i in impact["invariants"]]
    return "\n".join(lines)


def compile_context(phase: str, request: str, state: RunState) -> str:
    """
    #Feature: Context compilation
    #Scenario: Typed, compact outline of what earlier phases established, instead of pasting files
    #Complexity: Time O(s) - state size

    Args:
        phase: Phase about to run.
        request: The user's request.
        state: Current run state.

    Returns:
        First user message of the phase conversation.
    """
    parts = [_section("Request", request), _section("Snapshot", f"seq {state.snapshot_seq}, commit {state.commit}")]
    for name, title in ((a.PHASE_INTAKE, "Intake"), (a.PHASE_DISCOVER, "Context"), (a.PHASE_ANALYZE, "Analysis"),
                        (a.PHASE_PLAN, "Approved plan"), (a.PHASE_IMPLEMENT, "Patch set")):
        if name in state.artifacts and name != phase:
            parts.append(_section(title, json.dumps(state.artifacts[name], indent=1)))
    parts.append(_section("Impact", _impact(state)))
    if phase == a.PHASE_REPORT and state.verification:
        parts.append(_section("Verification", json.dumps(state.verification, indent=1)[:6000]))
    if phase == a.PHASE_REPORT:
        parts.append(_section("Handles issued in this run", ", ".join(state.handles[-80:])))
    parts.append(_section("Feedback", state.feedback))
    parts.append(_section("Phase goal", f"{phase}: call {a.SUBMIT_TOOLS[phase]} when done."))
    return "\n".join(p for p in parts if p)
