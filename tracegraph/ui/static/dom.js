// Everything renders through text nodes, so repository content can never become markup.
export function h(tag, props = {}, ...children) {
  const el = document.createElement(tag);
  for (const [name, value] of Object.entries(props || {})) {
    if (value === undefined || value === null || value === false) continue;
    if (name.startsWith("on")) el.addEventListener(name.slice(2).toLowerCase(), value);
    else if (name === "class") el.className = value;
    else if (name === "value") el.value = value;
    else if (value === true) el.setAttribute(name, "");
    else el.setAttribute(name, value);
  }
  el.append(...children.flat(Infinity).filter((c) => c !== null && c !== undefined && c !== false).map(
    (c) => (c instanceof Node ? c : document.createTextNode(String(c)))));
  return el;
}

export const badge = (text, kind = text) => h("span", { class: `badge s-${kind} c-${kind}` }, text);

export function table(columns, rows, { onRow, rowClass, empty = "Nothing here yet." } = {}) {
  if (!rows.length) return h("p", { class: "muted" }, empty);
  const body = h("tbody", {});
  rows.forEach((row) => {
    const cells = columns.map((c) => h("td", { class: c.class }, c.render ? c.render(row) : row[c.key]));
    const tr = h("tr", { class: [onRow ? "clickable" : "", rowClass ? rowClass(row) : ""].join(" ").trim() }, cells);
    if (onRow) tr.addEventListener("click", (event) => onRow(row, tr, event));
    body.append(tr);
  });
  return h("div", { class: "scroll-x" },
    h("table", {}, h("thead", {}, h("tr", {}, columns.map((c) => h("th", {}, c.title)))), body));
}

export const when = (iso) => (iso ? new Date(iso).toLocaleString() : "");

export function errorBox(error) {
  return h("div", { class: "error", role: "alert" }, error.message || String(error));
}

// Runs an async action, showing its failure in the slot and disabling the button while it runs.
export async function guarded(slot, button, action) {
  slot.replaceChildren();
  if (button) button.disabled = true;
  try {
    return await action();
  } catch (error) {
    slot.replaceChildren(errorBox(error));
    return undefined;
  } finally {
    if (button) button.disabled = false;
  }
}

export const field = (label, control) => h("label", { class: "field" }, label, control);

export function select(options, value, props = {}) {
  return h("select", props, options.map(([v, text]) => h("option", { value: v, selected: String(v) === String(value) }, text)));
}

// Repository and snapshot pickers shared by the impact, query and invariant pages.
export async function snapshotPicker(api, onChange) {
  const repos = (await api.repos()).items;
  const repoSelect = select(repos.map((r) => [r.id, `${r.id} - ${r.name}`]), repos[0]?.id);
  const snapshotSelect = h("select", {});
  async function loadSnapshots() {
    const items = repoSelect.value ? (await api.snapshots(repoSelect.value)).items.filter((s) => s.status === "ready") : [];
    snapshotSelect.replaceChildren(...items.map((s) => h("option", { value: s.id }, `seq ${s.seq} - ${s.commit_sha.slice(0, 12)}`)));
    onChange?.();
  }
  repoSelect.addEventListener("change", loadSnapshots);
  snapshotSelect.addEventListener("change", () => onChange?.());
  await loadSnapshots();
  return {
    el: h("div", { class: "row" }, field("Repository", repoSelect), field("Ready snapshot", snapshotSelect)),
    value: () => ({ repo_id: Number(repoSelect.value), snapshot_id: Number(snapshotSelect.value) }),
    ready: () => Boolean(repoSelect.value && snapshotSelect.value),
  };
}
