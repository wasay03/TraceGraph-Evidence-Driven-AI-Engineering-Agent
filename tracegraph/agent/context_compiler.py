import json
from pathlib import Path

from tracegraph.agent.state import RunState
from tracegraph.constants import agent as a
from tracegraph.engine.graph import GraphSnapshot


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


def repo_layout(graph: GraphSnapshot) -> str:
    """
    #Feature: Context compilation
    #Scenario: Python files of the snapshot and the Alembic head, so the model need not list directories
    #Complexity: Time O(n log n) - nodes, sorted
    """
    files = sorted({n.file for n in graph.of_type("Module") if n.file})
    shown = "\n".join(files[: a.MAX_LAYOUT_FILES]) + ("\n[more files omitted]" if len(files) > a.MAX_LAYOUT_FILES else "")
    followed = {e.src for edges in graph.fwd.get("PRECEDES", {}).values() for e in edges}
    heads = [m for m in graph.of_type("Migration") if m.id not in followed]
    head = "".join(f'\nAlembic head: revision = "{m.props.get("revision") or m.key}" in {m.file}. A new migration must set '
                   f'down_revision = "{m.props.get("revision") or m.key}" exactly (the revision string, not the file name).'
                   for m in heads)
    return _section("Repository layout", shown + head)


def scope_sources(root: Path, files: list[str]) -> str:
    """
    #Feature: Context compilation
    #Scenario: Current contents of the approved scope files, so implementing needs no read turns
    #Complexity: Time O(s) - file sizes, each capped
    """
    parts = []
    for name in files:
        path = root / name
        if path.is_file():
            text = path.read_text(encoding="utf-8", errors="replace")
            parts.append(f"--- {name}\n{text[: a.MAX_SCOPE_FILE_CHARS]}")
        else:
            parts.append(f"--- {name}\n(new file, does not exist yet)")
    return _section("Files in scope (current contents)", "\n".join(parts))


def compile_context(phase: str, request: str, state: RunState, repo: str = "") -> str:
    """
    #Feature: Context compilation
    #Scenario: Typed, compact outline of what earlier phases established, instead of pasting files
    #Complexity: Time O(s) - state size

    Args:
        phase: Phase about to run.
        request: The user's request.
        state: Current run state.
        repo: Rendered repository facts for this phase.

    Returns:
        First user message of the phase conversation.
    """
    parts = [_section("Request", request), _section("Snapshot", f"seq {state.snapshot_seq}, commit {state.commit}"), repo]
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
