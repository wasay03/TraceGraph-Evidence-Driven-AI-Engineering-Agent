import { api } from "../api.js";
import { badge, field, guarded, h, select, table, when } from "../dom.js";

async function snapshotsPanel(repo) {
  const slot = h("div", {});
  const tableSlot = h("div", {});
  const ref = h("input", { value: "HEAD", size: 12, "aria-label": "Git ref" });
  const kind = select([["full", "full"], ["incremental", "incremental"]], "full", { "aria-label": "Index kind" });
  async function refresh() {
    const { items } = await api.snapshots(repo.id);
    tableSlot.replaceChildren(table([
      { title: "Seq", key: "seq" },
      { title: "Commit", render: (s) => h("span", { class: "mono" }, s.commit_sha.slice(0, 12)) },
      { title: "Status", render: (s) => badge(s.status) },
      { title: "Nodes", render: (s) => s.stats.nodes ?? "" },
      { title: "Edges", render: (s) => s.stats.edges ?? "" },
      { title: "Holes", render: (s) => s.stats.coverage_holes_total ?? "" },
      { title: "Created", render: (s) => when(s.created_at) },
    ], items, { onRow: (s) => { location.hash = `#/snapshots/${s.id}`; }, empty: "Not indexed yet." }));
  }
  const button = h("button", { class: "primary", onclick: () => guarded(slot, button, async () => {
    await api.indexRepo(repo.id, { ref: ref.value, kind: kind.value });
    await refresh();
  }) }, "Index");
  await refresh();
  return h("section", { class: "panel" },
    h("div", { class: "row spread" }, h("div", {}, h("h2", {}, repo.name), h("div", { class: "muted small mono" }, repo.url)),
      h("div", { class: "row" }, ref, kind, button, h("button", { onclick: refresh }, "Refresh"))),
    h("p", { class: "muted small" }, "Indexing runs in the background worker (tg worker)."), slot, tableSlot);
}

export async function reposView() {
  const { items } = await api.repos();
  const slot = h("div", {});
  const url = h("input", { placeholder: "/absolute/path/to/repo", size: 44, "aria-label": "Repository path" });
  const add = h("button", { class: "primary", onclick: () => guarded(slot, add, async () => {
    await api.createRepo({ url: url.value });
    location.hash = "#/repos";
    window.dispatchEvent(new HashChangeEvent("hashchange"));
  }) }, "Register");
  const panels = await Promise.all(items.map(snapshotsPanel));
  return h("div", {}, h("h1", {}, "Repositories"),
    h("section", { class: "panel" }, h("h2", {}, "Register a local repository"), slot, h("div", { class: "row" }, url, add)),
    panels);
}

export async function snapshotView(id) {
  const snapshot = await api.snapshot(id);
  const validationSlot = h("div", {});
  const check = h("button", { onclick: () => guarded(validationSlot, check, async () => {
    const result = await api.validation(id);
    validationSlot.replaceChildren(result.valid ? h("p", { class: "s-passed" }, "Graph is valid: no dangling endpoints, signature or cardinality violations.")
      : table([{ title: "Violation", key: "violation" }, { title: "Edge type", key: "edge_type" }, { title: "Detail", key: "detail" }], result.violations));
  }) }, "Run validation");
  const by = (kind) => snapshot.counts.filter((c) => c.kind === kind);
  const counts = (title, kind) => h("section", { class: "panel" }, h("h2", {}, title),
    table([{ title: "Type", key: "type_name" }, { title: "Count", key: "total" }], by(kind)));
  return h("div", {},
    h("h1", {}, `Snapshot ${snapshot.seq} `, badge(snapshot.status)),
    h("section", { class: "panel" },
      h("div", { class: "mono small" }, snapshot.commit_sha),
      snapshot.error ? h("div", { class: "error" }, snapshot.error) : null,
      h("div", { class: "row" }, check), validationSlot),
    h("div", { class: "grid" }, counts("Nodes", "node"), counts("Edges", "edge")),
    h("section", { class: "panel" }, h("h2", {}, `Coverage holes (${snapshot.coverage_holes.length})`),
      table([
        { title: "Kind", key: "kind" },
        { title: "Location", render: (c) => (c.file_path ? `${c.file_path}:${c.line_start}` : "") },
        { title: "Detail", class: "mono", render: (c) => JSON.stringify(c.detail) },
      ], snapshot.coverage_holes, { empty: "No coverage holes." })));
}
