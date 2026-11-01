import { api } from "../api.js";
import { badge, guarded, h, select, snapshotPicker, table } from "../dom.js";
import { derivationGraph } from "../graph.js";

const endpoints = { op: "select", type: "Endpoint" };
const EXAMPLES = {
  "Tables each endpoint writes": { op: "reach", input: endpoints, rpq: "HANDLED_BY . (CALLS|INJECTS)* . WRITES_TO", target_types: ["Table"] },
  "Endpoints no test reaches": { op: "not_exists", scope: endpoints, rpq: "HANDLED_BY . CALLED_BY* . TESTED_BY", target_types: ["Test"] },
  "Tables by number of writers": { op: "aggregate", groups: { op: "select", type: "Table" }, rpq: "WRITTEN_BY", target_types: ["Callable"] },
  "Most-called callables": { op: "rank", input: { op: "select", type: "Callable" }, score: "fan_in", edges: ["CALLS"], k: 10 },
  "Import cycles": { op: "scc", input: { op: "select", type: "Module" }, edge: "IMPORTS" },
  "DSL: untested writing endpoints": { op: "dsl", rule_pack: "core", text: "?- untested_writer(E)." },
  "DSL: tables by writing endpoints": { op: "dsl", text: "?- aggregate(T, count_distinct(E)) :- Endpoint(E), HANDLED_BY(E, H), reach(H, F, \"CALLS*\"), WRITES_TO(F, T), Table(T) order by 2 desc limit 10." },
  "Match: code assuming a nullable column": { op: "match", nodes: [{ var: "F", type: "Callable" }, { var: "C", type: "Column", where: { nullable: true } }], edges: [{ src: "F", dst: "C", rpq: "ASSUMES_NOT_NULL . MAPS_TO" }] },
  "Why not: is calculate_total reached in 1 hop?": { op: "why_not", expected: "app.services.calculate_total", query: { op: "reach", input: { op: "select", type: "Endpoint", where: { key: "POST /orders" } }, rpq: "HANDLED_BY . CALLS*", max_hops: 1 } },
  "Diff: nullable columns after a change": { op: "diff", query: { op: "select", type: "Column", where: { nullable: true } }, changes: [{ kind: "make_column_nullable", column: "orders.total" }] },
  "Check invariants": { op: "check", invariants: [] },
};

function resultText(row) {
  if (row.predicate) return `${row.predicate}(${row.nodes.map((n) => n.key).join(", ")})`;
  if (row.node) return `${row.node.type} ${row.node.key}`;
  if (row.bindings) return Object.entries(row.bindings).map(([v, n]) => `${v}=${n.key}`).join("  ");
  if (row.key) return `${row.type} ${row.key}`;
  return (row.nodes || []).map((n) => n.key).join(" -> ");
}

function renderAnswer(answer) {
  const extra = [...new Set(answer.rows.flatMap((r) => Object.keys(r)))].filter((k) => !["node", "source", "nodes", "gaps", "component", "bindings", "predicate", "key", "type"].includes(k));
  const graph = h("div", {}, h("p", { class: "muted small" }, "Select a row to see its witness path."));
  const rows = answer.rows.map((row, index) => ({ row, derivation: answer.derivations.find((d) => d.row === index) }));
  return h("div", {},
    h("p", {}, badge(answer.truth), ` ${answer.rows.length} rows, ${answer.latency_ms} ms`, answer.truncated ? " (truncated)" : "",
      h("span", { class: "mono small muted" }, `  ${answer.handle}`)),
    h("div", { class: "grid" },
      h("section", { class: "panel" }, table([
        { title: "Result", class: "key mono", render: ({ row }) => resultText(row) },
        ...extra.map((k) => ({ title: k, render: ({ row }) => String(row[k] ?? "") })),
        { title: "Holes", class: "small", render: ({ row }) => (row.gaps || []).map((g) => g.kind).join(", ") },
      ], rows, { onRow: ({ derivation }) => {
        graph.replaceChildren(derivation ? derivationGraph(derivation.path) : h("p", { class: "muted small" }, "This row is an anchor, so it has no path."));
      }, empty: "No rows." })),
      h("section", { class: "panel" }, h("h2", {}, "Witness path"), graph)),
    answer.coverage_gaps.length ? h("section", { class: "panel" }, h("h2", {}, "Coverage gaps"),
      h("ul", { class: "plain small" }, answer.coverage_gaps.map((g) => h("li", {}, `${g.node}: ${g.kind}`)))) : null);
}

export async function queryView() {
  const slot = h("div", {});
  const results = h("div", {});
  const picker = await snapshotPicker(api);
  const editor = h("textarea", { rows: 10, spellcheck: "false", "aria-label": "Query IR" });
  const names = Object.keys(EXAMPLES);
  const example = select(names.map((n) => [n, n]), names[0], { "aria-label": "Example" });
  const load = () => { editor.value = JSON.stringify(EXAMPLES[example.value], null, 2); };
  example.addEventListener("change", load);
  load();
  const run = h("button", { class: "primary", onclick: () => guarded(slot, run, async () => {
    const query = JSON.parse(editor.value);
    results.replaceChildren(renderAnswer(await api.query({ ...picker.value(), query })));
  }) }, "Run query");
  return h("div", {}, h("h1", {}, "Query the graph"),
    h("section", { class: "panel" }, h("p", { class: "muted small" }, "Typed IR over the graph: no model calls and no quota used."),
      slot, picker.el, h("div", { class: "row" }, example), editor, h("div", { class: "row" }, run)), results);
}
