const KEY_NAME = "tracegraph.apiKey";

export function getKey() {
  try { return sessionStorage.getItem(KEY_NAME) || ""; } catch { return ""; }
}

export function setKey(value) {
  try { sessionStorage.setItem(KEY_NAME, value); } catch { /* the key then lasts for this page only */ }
}

async function request(method, path, body) {
  const headers = { "X-API-Key": getKey() };
  if (body !== undefined) headers["Content-Type"] = "application/json";
  const response = await fetch(path, { method, headers, body: body === undefined ? undefined : JSON.stringify(body) });
  const data = await response.json().catch(() => ({}));
  if (!response.ok) {
    const error = data.error || {};
    const detail = error.details?.errors?.map((e) => `${e.loc.join(".")}: ${e.msg}`).join("; ");
    const failure = new Error(detail || error.message || `${method} ${path} failed (${response.status})`);
    failure.status = response.status;
    throw failure;
  }
  return data;
}

export const api = {
  health: () => request("GET", "/health"),
  ontology: () => request("GET", "/ontology"),
  repos: () => request("GET", "/repos?limit=100"),
  createRepo: (body) => request("POST", "/repos", body),
  snapshots: (repoId) => request("GET", `/repos/${repoId}/snapshots?limit=50`),
  indexRepo: (repoId, body) => request("POST", `/repos/${repoId}/snapshots`, body),
  snapshot: (id) => request("GET", `/snapshots/${id}`),
  validation: (id) => request("GET", `/snapshots/${id}/validation`),
  source: (id, path, start, end) =>
    request("GET", `/snapshots/${id}/source?path=${encodeURIComponent(path)}&start=${start}&end=${end}`),
  query: (body) => request("POST", "/query", body),
  answer: (handle) => request("GET", `/answers/${handle}`),
  impact: (body) => request("POST", "/impact", body),
  impactReport: (handle) => request("GET", `/impact/${handle}`),
  invariants: (body) => request("POST", "/invariants/check", body),
  runs: () => request("GET", "/runs?limit=50"),
  run: (id, after = 0) => request("GET", `/runs/${id}?events_after=${after}`),
  startRun: (body) => request("POST", "/runs", body),
  approve: (id, body) => request("POST", `/runs/${id}/approval`, body),
  clarify: (id, body) => request("POST", `/runs/${id}/clarify`, body),
  retry: (id, body) => request("POST", `/runs/${id}/retry`, body),
};
