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
};

function renderAnswer(answer) {
  const extra = [...new Set(answer.rows.flatMap((r) => Object.keys(r)))].filter((k) => !["node", "source", "nodes", "gaps", "component"].includes(k));
  const graph = h("div", {}, h("p", { class: "muted small" }, "Select a row to see its witness path."));
  const rows = answer.rows.map((row, index) => ({ row, derivation: answer.derivations.find((d) => d.row === index) }));
  return h("div", {},
    h("p", {}, badge(answer.truth), ` ${answer.rows.length} rows, ${answer.latency_ms} ms`, answer.truncated ? " (truncated)" : "",
      h("span", { class: "mono small muted" }, `  ${answer.handle}`)),
    h("div", { class: "grid" },
      h("section", { class: "panel" }, table([
        { title: "Result", class: "key mono", render: ({ row }) => (row.node ? `${row.node.type} ${row.node.key}` : (row.nodes || []).map((n) => n.key).join(" -> ")) },
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
