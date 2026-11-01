from pathlib import Path

from opentelemetry import trace
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import SimpleSpanProcessor
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter

from tests.engine.helpers import shop_graph
from tracegraph.agent.state import RunState
from tracegraph.core.tracing import sql_function
from tracegraph.engine import Evaluator, build_answer
from tracegraph.tools import ToolContext, get_tool_registry


class _Query:
    async def answer_for(self, graph, query, query_ir, max_rows):
        return build_answer(graph, Evaluator(graph).evaluate(query), "h", max_rows, {})


class _Services:
    query = _Query()


def test_sql_span_names_the_stored_function():
    assert sql_function("SELECT * FROM tg_node_list_at(:repo, :seq)") == "tg_node_list_at"
    assert sql_function("SELECT 1") == "sql"


async def test_tool_span_contains_engine_operator_spans():
    exporter = InMemorySpanExporter()
    provider = TracerProvider()
    provider.add_span_processor(SimpleSpanProcessor(exporter))
    tracer = provider.get_tracer("test")
    original = trace.get_tracer
    trace.get_tracer = lambda *args, **kwargs: tracer  # the global provider can only be set once per process
    try:
        ctx = ToolContext(1, "analyze", "A4", RunState(), shop_graph(), _Services(), Path("."))
        result = await get_tool_registry().call(ctx, "aggregate", {"group_type": "Table", "rpq": "WRITTEN_BY"})
    finally:
        trace.get_tracer = original
    assert result.ok
    spans = {s.name: s for s in exporter.get_finished_spans()}
    assert spans["engine aggregate"].parent.span_id == spans["tool aggregate"].context.span_id
    assert spans["engine select"].parent.span_id == spans["engine aggregate"].context.span_id
    assert spans["tool aggregate"].attributes["run.phase"] == "analyze"
