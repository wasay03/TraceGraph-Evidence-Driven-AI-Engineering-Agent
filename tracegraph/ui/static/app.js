import { api, getKey, setKey } from "./api.js";
import { errorBox, h } from "./dom.js";
import { impactView } from "./views/impact.js";
import { ontologyView } from "./views/ontology.js";
import { queryView } from "./views/query.js";
import { reposView, snapshotView } from "./views/repos.js";
import { runDetailView, runsView } from "./views/runs.js";

const NAV = [["repos", "Repositories"], ["runs", "Agent runs"], ["impact", "Impact"], ["query", "Query"], ["ontology", "Ontology"]];
const view = document.getElementById("view");
let cancelCurrent = null;

const ROUTES = [
  [/^repos$/, () => reposView()],
  [/^snapshots\/(\d+)$/, (m) => snapshotView(Number(m[1]))],
  [/^runs$/, () => runsView()],
  [/^runs\/(\d+)$/, (m) => runDetailView(Number(m[1]))],
  [/^impact(?:\/(ans_[0-9a-f]+))?$/, (m) => impactView(m[1])],
  [/^query$/, () => queryView()],
  [/^ontology$/, () => ontologyView()],
];

function renderNav(active) {
  document.getElementById("nav").replaceChildren(...NAV.map(([path, label]) =>
    h("a", { href: `#/${path}`, class: active.startsWith(path) || (path === "repos" && active.startsWith("snapshots")) ? "active" : "" }, label)));
}

async function route() {
  const path = location.hash.replace(/^#\/?/, "") || "repos";
  renderNav(path);
  cancelCurrent?.();
  cancelCurrent = null;
  const match = ROUTES.map(([re, fn]) => [path.match(re), fn]).find(([m]) => m);
  view.replaceChildren(h("p", { class: "muted" }, "Loading..."));
  if (!match) {
    view.replaceChildren(errorBox(new Error(`Unknown page: ${path}`)));
    return;
  }
  try {
    const rendered = await match[1](match[0]);
    cancelCurrent = rendered.cancel || null;
    view.replaceChildren(rendered.el || rendered);
  } catch (error) {
    const hint = error.status === 401 ? " Enter your API key at the top of the page." : "";
    view.replaceChildren(errorBox(new Error(error.message + hint)));
  }
}

async function checkHealth() {
  const dot = document.getElementById("health");
  try {
    const health = await api.health();
    dot.className = `dot ${health.status === "ok" ? "ok" : "bad"}`;
    dot.title = `API ${health.status}, database ${health.database}`;
  } catch {
    dot.className = "dot bad";
    dot.title = "API unreachable";
  }
}

const keyInput = document.getElementById("api-key");
keyInput.value = getKey();
document.getElementById("key-form").addEventListener("submit", (event) => {
  event.preventDefault();
  setKey(keyInput.value);
  route();
});
keyInput.addEventListener("change", () => { setKey(keyInput.value); route(); });
window.addEventListener("hashchange", route);
checkHealth();
route();
