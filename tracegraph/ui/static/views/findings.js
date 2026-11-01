import { api } from "../api.js";
import { badge, errorBox, h, table } from "../dom.js";
import { derivationGraph } from "../graph.js";

const CLASSES = ["BREAKS", "UNKNOWN", "AT_RISK", "GUARDED"];

function sourceBlock(snapshotId, evidence) {
  const slot = h("div", {});
  const label = `${evidence.file}:${evidence.lines[0]}-${evidence.lines[1]} (${evidence.extractor}/${evidence.method})`;
  if (!snapshotId) return h("div", { class: "mono small" }, label);
  const open = h("button", { onclick: async () => {
    open.disabled = true;
    try {
      const start = Math.max(evidence.lines[0] - 2, 1);
      const source = await api.source(snapshotId, evidence.file, start, evidence.lines[1] + 2);
      slot.replaceChildren(h("pre", {}, source.lines.map((line, i) => `${String(source.start + i).padStart(5)}  ${line}`).join("\n")));
    } catch (error) {
      slot.replaceChildren(errorBox(error));
      open.disabled = false;
    }
  } }, "Source");
  return h("div", {}, h("div", { class: "row small mono" }, label, open), slot);
}

function findingDetail(finding, snapshotId) {
  return h("div", {},
    h("p", { class: "small" }, `Rule ${finding.rule}, change ${finding.change}, weakest tier ${finding.weakest_tier}.`),
    derivationGraph(finding.path),
    finding.evidence.length ? h("h2", {}, "Evidence") : h("p", { class: "muted small" }, "No source evidence on this path."),
    finding.evidence.map((e) => sourceBlock(snapshotId, e)));
}

// Findings table (PRD 13.3): class, tier, distance and score, with the derivation and evidence on selection.
export function findingsPanel(report, snapshotId) {
  const active = new Set(CLASSES);
  const tableSlot = h("div", {});
  const detail = h("div", {}, h("p", { class: "muted" }, "Select a finding to see its derivation and source."));
  function render() {
    const rows = report.findings.filter((f) => active.has(f.cls));
    tableSlot.replaceChildren(table([
      { title: "Class", render: (f) => badge(f.cls) },
      { title: "Type", render: (f) => f.node.type },
      { title: "Symbol", class: "key mono", render: (f) => f.node.key },
      { title: "Reason", class: "small", key: "reason" },
      { title: "Tier", key: "weakest_tier" },
      { title: "Dist.", key: "distance" },
      { title: "Score", key: "score" },
    ], rows, {
      empty: "No findings in the selected classes.",
      onRow: (f, tr) => {
        tr.parentElement.querySelectorAll(".selected").forEach((el) => el.classList.remove("selected"));
        tr.classList.add("selected");
        detail.replaceChildren(findingDetail(f, snapshotId));
      },
    }));
  }
  const filters = CLASSES.map((cls) => {
    const count = report.findings.filter((f) => f.cls === cls).length;
    const box = h("input", { type: "checkbox", checked: true, onchange: (e) => {
      if (e.target.checked) active.add(cls); else active.delete(cls);
      render();
    } });
    return h("label", { class: "row small" }, box, badge(`${cls} ${count}`, cls));
  });
  render();
  return h("div", { class: "grid" },
    h("section", { class: "panel" }, h("div", { class: "row" }, h("h2", {}, "Findings"), filters), tableSlot),
    h("section", { class: "panel" }, h("h2", {}, "Derivation"), detail));
}

export function reportPanels(report, snapshotId) {
  return h("div", {},
    findingsPanel(report, snapshotId),
    h("div", { class: "grid" },
      h("section", { class: "panel" }, h("h2", {}, "Obligations"), table([
        { title: "Kind", key: "kind" }, { title: "Target", class: "key mono", render: (o) => o.target.key },
        { title: "Detail", class: "small", key: "detail" }], report.obligations, { empty: "None." })),
      h("section", { class: "panel" }, h("h2", {}, "Tests to run"), table([
        { title: "Test", class: "key mono", render: (t) => t.node.key }, { title: "Score", key: "score" }], report.tests, { empty: "None selected." })),
      h("section", { class: "panel" }, h("h2", {}, "Invariant changes"), table([
        { title: "Status", render: (i) => badge(i.status, i.status === "new" ? "failed" : "passed") },
        { title: "Invariant", key: "invariant" }, { title: "Message", class: "small key", key: "message" }], report.invariants, { empty: "None." })),
      h("section", { class: "panel" }, h("h2", {}, "Coverage gaps"), table([
        { title: "Node", class: "key mono", key: "node" }, { title: "Kind", key: "kind" }], report.coverage_gaps, { empty: "None on this change." }))));
}
