from typing import Any

from pydantic import BaseModel, ConfigDict

from tracegraph.engine import Evaluator, ir
from tracegraph.engine.answer import Answer
from tracegraph.engine.graph import NodeView
from tracegraph.errors import Errors
from tracegraph.tools.registry import ToolContext, ToolOutput

MAX_ROWS = 60


class ToolInput(BaseModel):
    """
    #Feature: Tool catalog
    #Scenario: Base for tool inputs; unknown fields are rejected
    #Complexity: Time O(1) - constant
    """

    model_config = ConfigDict(extra="forbid")


def resolve_ref(ctx: ToolContext, ref: str, types: tuple[str, ...] = ("Entity",)) -> NodeView:
    """
    #Feature: Tool catalog
    #Scenario: Exact natural key of the given types; otherwise refuse with ranked candidates (never guess)
    #Complexity: Time O(n) - scan of nodes

    Raises:
        Errors.HTTP.BadRequest: When the reference is not an exact key.
    """
    graph = ctx.graph
    exact = [n for n in graph.nodes.values() if n.key == ref and any(graph.registry.is_subtype(n.type, t) for t in types)]
    if len(exact) == 1:
        return exact[0]
    candidates = Evaluator(graph).evaluate(ir.Resolve(text=ref, types=list(types), limit=5)).rows or []
    names = [f"{graph.nodes[c['node']].type} {graph.nodes[c['node']].key}" for c in candidates]
    raise Errors.HTTP.BadRequest(f"{ref!r} is not an exact {'/'.join(types)} key. Candidates: {names or 'none'}")


def node_line(row: dict[str, Any]) -> str:
    """
    #Feature: Tool catalog
    #Scenario: One compact line per answer row: Type key (file:line) plus scalar extras
    #Complexity: Time O(1) - constant
    """
    node = row.get("node") or {}
    where = f" ({node.get('file')}:{node.get('line')})" if node.get("file") else ""
    extras = " ".join(f"{k}={v}" for k, v in row.items() if k not in ("node", "source", "nodes", "gaps")
                      and not isinstance(v, (dict, list)))
    gaps = f" gaps={[g['kind'] for g in row['gaps']]}" if row.get("gaps") else ""
    return f"{node.get('type', '?')} {node.get('key', '?')}{where}{(' ' + extras) if extras else ''}{gaps}"


def _row_line(row: dict[str, Any]) -> str:
    """
    #Feature: Tool catalog
    #Scenario: Derived tuples, pattern bindings, diff rows and cycles each print in their own shape
    #Complexity: Time O(1) - constant
    """
    truth = f" truth={row['truth']}" if row.get("truth") else ""
    if "predicate" in row:
        return f"{row['predicate']}({', '.join(n['key'] for n in row['nodes'])}){truth}"
    if "nodes" in row:
        return "cycle: " + " -> ".join(n["key"] for n in row["nodes"])
    if "bindings" in row and "node" not in row:
        return " ".join(f"{var}={n['key']}" for var, n in row["bindings"].items()) + truth
    if "change" in row:
        return f"{row['change']} {row.get('type', '')} {row.get('key', '')}"
    return node_line(row)


def render_answer(answer: Answer, title: str) -> str:
    """
    #Feature: Tool catalog
    #Scenario: Compact answer rendering: truth, rows, truncation and coverage gaps (evidence via get_evidence)
    #Complexity: Time O(r) - rows
    """
    lines = [f"{title}: truth={answer.truth} rows={len(answer.rows)}"]
    for row in answer.rows[:MAX_ROWS]:
        lines.append("  " + _row_line(row))
    if answer.truncated or len(answer.rows) > MAX_ROWS:
        lines.append("  [truncated]")
    if answer.coverage_gaps:
        lines.append("  coverage gaps: " + ", ".join(f"{g.node}:{g.kind}" for g in answer.coverage_gaps[:10]))
    return "\n".join(lines)


async def ask(ctx: ToolContext, query: Any, title: str) -> ToolOutput:
    """
    #Feature: Tool catalog
    #Scenario: Evaluate IR on the run's snapshot, persist the Answer and render it with its handle
    #Complexity: Time per query
    """
    query_ir = query.model_dump(mode="json")
    answer = await ctx.services.query.answer_for(ctx.graph, query, query_ir, MAX_ROWS * 2)
    return ToolOutput(render_answer(answer, title), answer.handle, {"truth": answer.truth})


def select_key(node: NodeView) -> ir.Select:
    """
    #Feature: Tool catalog
    #Scenario: Anchor IR for one node
    #Complexity: Time O(1) - constant
    """
    return ir.Select(type=node.type, where={"key": node.key})
