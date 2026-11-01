import { api } from "../api.js";
import { badge, field, guarded, h, select, snapshotPicker, table } from "../dom.js";
import { reportPanels } from "./findings.js";

const KINDS = {
  make_column_nullable: [["column", "Column", "orders.status"]],
  drop_column: [["column", "Column", "orders.status"]],
  add_enum_member: [["enum", "Enum class", "app.models.OrderStatus"], ["member", "Member", "CANCELLED"], ["value", "Value", "cancelled"]],
  change_return_type: [["function", "Function", "app.services.calculate_total"], ["new_type", "New type", "int | None"]],
  change_signature: [["function", "Function", "app.services.get_discount"], ["add", "Add parameter (name)", "tenant_id"], ["remove", "Remove parameter (name)", ""]],
  remove_symbol: [["symbol", "Symbol", "app.repository.OrderRepository.get"]],
  modify_body: [["function", "Function", "app.services.get_discount"]],
};

function specFrom(kind, inputs) {
  const spec = { kind };
  for (const [name, input] of Object.entries(inputs)) {
    if (!input.value) continue;
    if (name === "add") spec.add = [{ name: input.value }];
    else if (name === "remove") spec.remove = [input.value];
    else spec[name] = input.value;
  }
  return spec;
}

function invariantsPanel(picker) {
  const slot = h("div", {});
  const button = h("button", { onclick: () => guarded(slot, button, async () => {
    const result = await api.invariants({ repo_id: picker.value().repo_id, snapshot_id: picker.value().snapshot_id });
    slot.replaceChildren(h("p", {}, "All invariants hold: ", badge(result.truth)), table([
      { title: "Invariant", key: "invariant" }, { title: "Severity", key: "severity" },
      { title: "Truth", render: (v) => badge(v.truth === "TRUE" ? "definite" : v.truth, v.truth === "TRUE" ? "failed" : "UNKNOWN") },
      { title: "Where", class: "key mono", render: (v) => v.node.key }, { title: "Message", class: "small key", key: "message" },
    ], result.violations, { empty: "No violations." }));
  }) }, "Check invariants on this snapshot");
  return h("section", { class: "panel" }, h("h2", {}, "Invariants"), button, slot);
}

export async function impactView(handle) {
  const slot = h("div", {});
  const results = h("div", {});
  const picker = await snapshotPicker(api);
  if (handle) {
    const report = await api.impactReport(handle);
    results.replaceChildren(h("h2", {}, `Report ${handle}`), reportPanels(report, null));
  }
  const kind = select(Object.keys(KINDS).map((k) => [k, k]), "make_column_nullable", { "aria-label": "Change kind" });
  const fields = h("div", { class: "row" });
  let inputs = {};
  function renderFields() {
    inputs = {};
    fields.replaceChildren(...KINDS[kind.value].map(([name, label, placeholder]) => {
      inputs[name] = h("input", { placeholder, size: 30 });
      return field(label, inputs[name]);
    }));
  }
  kind.addEventListener("change", renderFields);
  renderFields();
  const run = h("button", { class: "primary", onclick: () => guarded(slot, run, async () => {
    const report = await api.impact({ ...picker.value(), changes: [specFrom(kind.value, inputs)] });
    const summary = Object.entries(report.summary).map(([k, v]) => `${k}: ${v}`).join("  ");
    results.replaceChildren(h("p", { class: "small muted" }, `${summary}  (${report.latency_ms} ms, overlay ${report.overlay})`),
      reportPanels(report, picker.value().snapshot_id));
  }) }, "Simulate");
  return h("div", {}, h("h1", {}, "Impact analysis"),
    h("section", { class: "panel" }, h("h2", {}, "What if..."), h("p", { class: "muted small" }, "Runs on the graph only: no model calls and no quota used."),
      slot, picker.el, h("div", { class: "row" }, field("Change", kind), fields), h("div", { class: "row" }, run))
    , results, invariantsPanel(picker));
}
