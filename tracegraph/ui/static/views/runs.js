import { api } from "../api.js";
import { badge, errorBox, field, guarded, h, select, table, when } from "../dom.js";
import { reportPanels } from "./findings.js";

const PHASES = ["intake", "discover", "analyze", "plan", "approval", "implement", "verify", "report"];
const ACTIVE = new Set(["queued", "running"]);
const POLL_MS = 3000;

function newRunPanel(repos, onStarted) {
  const slot = h("div", {});
  const repo = select(repos.map((r) => [r.id, `${r.id} - ${r.name}`]), repos[0]?.id, { "aria-label": "Repository" });
  const mode = select([["interactive", "interactive (pause for approval)"], ["benchmark", "benchmark (auto-approve)"]], "interactive");
  const config = select(["A4", "A3", "A2", "A1", "B0"].map((c) => [c, c]), "A4");
  const request = h("textarea", { rows: 3, placeholder: "Add a CANCELLED order status...", "aria-label": "Request" });
  const start = h("button", { class: "primary", onclick: () => guarded(slot, start, async () => {
    const run = await api.startRun({ repo_id: Number(repo.value), request: request.value, mode: mode.value, config: config.value });
    onStarted(run);
  }) }, "Start run");
  return h("section", { class: "panel" }, h("h2", {}, "New run"),
    h("p", { class: "muted small" }, "Each run spends model requests from your API quota, up to the per-run cap (TG_LLM_MAX_CALLS_PER_RUN)."),
    slot, h("div", { class: "row" }, field("Repository", repo), field("Mode", mode), field("Tools", config)), request,
    h("div", { class: "row" }, start));
}

export async function runsView() {
  const [{ items: repos }, { items: runs }] = await Promise.all([api.repos(), api.runs()]);
  return h("div", {}, h("h1", {}, "Agent runs"),
    newRunPanel(repos, (run) => { location.hash = `#/runs/${run.id}`; }),
    h("section", { class: "panel" }, table([
      { title: "Run", key: "id" }, { title: "Status", render: (r) => badge(r.status) }, { title: "Phase", key: "phase" },
      { title: "Tools", key: "config" }, { title: "Request", class: "key", key: "request" },
      { title: "Model calls", render: (r) => `${r.budget.llm_calls ?? 0}/${r.budget.max_llm_calls ?? "?"}` },
      { title: "Updated", class: "small", render: (r) => when(r.updated_at) },
    ], runs, { onRow: (r) => { location.hash = `#/runs/${r.id}`; }, empty: "No runs yet." })));
}

function timeline(run) {
  const done = new Set(run.state.phase_history || []);
  return h("ol", { class: "timeline", "aria-label": "Phases" }, PHASES.map((phase) =>
    h("li", { class: phase === run.phase && run.status !== "completed" ? "current" : (done.has(phase) ? "done" : "") }, phase)));
}

function meter(label, used, max) {
  const pct = max ? Math.min(100, Math.round((100 * used) / max)) : 0;
  return h("div", { class: "stat" }, h("span", { class: "small muted" }, label), h("b", {}, max ? `${used} / ${max}` : used),
    max ? h("div", { class: "meter" }, h("div", { style: `width:${pct}%` })) : null);
}

function budgetPanel(run) {
  const b = run.state.budget || {};
  return h("section", { class: "panel" }, h("h2", {}, "Budget"), h("div", { class: "row" },
    meter("Model calls", b.llm_calls ?? 0, b.max_llm_calls), meter("Tool calls", b.tool_calls ?? 0, 150),
    meter("Input tokens", b.input_tokens ?? 0), meter("Output tokens", b.output_tokens ?? 0),
    meter("Correction rounds", run.state.correction_rounds ?? 0, 3)));
}

function eventLog(events) {
  const shown = events.filter((e) => e.kind !== "llm_turn");
  return h("section", { class: "panel" }, h("h2", {}, `Activity (${events.filter((e) => e.kind === "llm_turn").length} model turns, ${events.filter((e) => e.kind === "tool_call").length} tool calls)`),
    table([
      { title: "#", key: "seq" }, { title: "Phase", key: "phase" },
      { title: "Event", render: (e) => (e.kind === "tool_call" ? e.payload.tool : e.payload.retry ? "resume" : e.kind) },
      { title: "Result", render: (e) => {
        if (e.kind === "tool_call") return e.payload.ok ? badge("ok", "passed") : badge(e.payload.error || "error", "failed");
        if (e.kind === "transition") return `-> ${e.payload.to} (${e.payload.status})`;
        return "";
      } },
      { title: "Detail", class: "mono small key", render: (e) => {
        if (e.kind === "transition") return "";
        if (e.payload.error === "Rejected") return e.payload.detail;
        return JSON.stringify(e.kind === "tool_call" ? e.payload.input : e.payload).slice(0, 220);
      } },
      { title: "ms", render: (e) => e.payload.latency_ms ?? "" },
    ], [...shown].reverse().slice(0, 150), { empty: "Nothing yet." }));
}

function coverage(plan, impact) {
  const served = new Set(plan.steps.flatMap((s) => [...s.serves, ...s.targets]));
  const accepted = new Set((plan.accepted_risks || []).map((r) => r.node));
  const breaks = (impact?.findings || []).filter((f) => f.cls === "BREAKS");
  const line = (label, ok, note) => h("li", {}, h("span", { class: ok ? "covered" : "uncovered" }, ok ? "covered " : "not covered "), label, note ? h("span", { class: "muted small" }, ` (${note})`) : null);
  return h("div", {}, h("h2", {}, "What the plan must cover"), impact ? h("ul", { class: "plain" },
    breaks.map((f) => line(`BREAKS ${f.key}`, served.has(f.key) || accepted.has(f.key), accepted.has(f.key) ? "accepted risk" : f.reason)),
    impact.obligations.map((o) => line(`obligation ${o.kind} on ${o.target}`, served.has(o.kind) || served.has(o.target), o.detail)),
    !breaks.length && !impact.obligations.length ? h("li", { class: "muted" }, "No BREAKS findings or obligations.") : null)
    : h("p", { class: "muted small" }, "This run did not simulate the change, so there are no findings to compare."));
}

function approvalPanel(run, refresh) {
  const plan = run.state.artifacts?.plan;
  if (!plan) return null;
  const awaiting = run.status === "awaiting_approval";
  const slot = h("div", {});
  const comment = h("input", { placeholder: "Comment (optional)", size: 40, "aria-label": "Comment" });
  const editor = h("textarea", { rows: 10, spellcheck: "false", "aria-label": "Plan JSON", value: JSON.stringify(plan, null, 2) });
  const decide = (approved, edited, button) => guarded(slot, button, async () => {
    const body = { approved, comment: comment.value || null };
    if (edited) body.plan = JSON.parse(editor.value);
    await api.approve(run.id, body);
    await refresh();
  });
  const approve = h("button", { class: "primary", onclick: () => decide(true, false, approve) }, "Approve");
  const approveEdited = h("button", { onclick: () => decide(true, true, approveEdited) }, "Approve edited plan");
  const reject = h("button", { class: "danger", onclick: () => decide(false, false, reject) }, "Reject");
  return h("section", { class: "panel" },
    h("div", { class: "row spread" }, h("h2", {}, "Plan"), run.state.approval ? badge(run.state.approval.approved ? `approved by ${run.state.approval.by}` : "rejected", run.state.approval.approved ? "passed" : "failed") : (awaiting ? badge("awaiting approval", "awaiting_approval") : null)),
    h("div", { class: "grid" },
      h("div", {}, table([
        { title: "Step", key: "id" }, { title: "What", key: "description" },
        { title: "Files", class: "mono small key", render: (s) => s.files.join(", ") },
        { title: "Serves", class: "small key", render: (s) => s.serves.join(", ") },
      ], plan.steps), h("p", { class: "small muted" }, `Tests: ${(plan.tests || []).join(", ") || "none"}`),
      (plan.accepted_risks || []).length ? h("p", { class: "small" }, `Accepted risks: ${plan.accepted_risks.map((r) => `${r.node} (${r.reason})`).join("; ")}`) : null),
      coverage(plan, run.state.impact)),
    awaiting ? h("div", {}, slot, editor, h("div", { class: "row" }, comment, approve, approveEdited, reject)) : null);
}

function verificationPanel(run) {
  const v = run.state.verification;
  if (!v) return null;
  const c = v.conformance || {};
  const list = (title, items) => h("div", {}, h("h2", {}, `${title} (${(items || []).length})`), (items || []).length
    ? h("ul", { class: "plain small mono" }, items.map((i) => h("li", {}, i))) : h("p", { class: "muted small" }, "None."));
  return h("section", { class: "panel" }, h("div", { class: "row spread" }, h("h2", {}, "Verification"), badge(v.passed ? "passed" : "failed")),
    table([
      { title: "Rung", key: "rung" }, { title: "Check", key: "name" }, { title: "Status", render: (r) => badge(r.status) },
      { title: "Detail", class: "mono small key", render: (r) => (r.detail ? h("details", {}, h("summary", {}, "show"), h("pre", {}, typeof r.detail === "string" ? r.detail : JSON.stringify(r.detail, null, 2))) : "") },
    ], v.rungs),
    h("div", { class: "grid" }, list("Changed symbols", c.changed_symbols), list("Scope creep", c.scope_creep),
      list("Unresolved breaks", c.unresolved_breaks), list("New violations", c.new_violations),
      h("div", {}, h("h2", {}, "Obligations"), h("ul", { class: "plain small" }, Object.entries(c.obligations || {}).map(([k, s]) => h("li", {}, badge(s), ` ${k}`))))));
}

function reportPanel(run) {
  const report = run.state.artifacts?.report;
  if (!report) return null;
  return h("section", { class: "panel" }, h("h2", {}, "Report"), h("p", {}, report.summary),
    table([
      { title: "Claim", key: "text" }, { title: "Truth", render: (c) => (c.truth ? badge(c.truth, c.truth === "ROWS" ? "passed" : c.truth) : "") },
      { title: "Evidence", class: "mono small", render: (c) => c.handle },
    ], report.claims));
}

function patchesPanel(run) {
  const patches = run.state.patches || [];
  if (!patches.length) return null;
  return h("section", { class: "panel" }, h("h2", {}, `Patches (${patches.length})`), patches.map((p) =>
    h("details", {}, h("summary", { class: "mono small" }, `${p.patch_id} ${p.step_id || ""} - ${p.files.join(", ")}`), h("pre", {}, p.diff))));
}

function actionPanel(run, refresh) {
  const slot = h("div", {});
  if (["failed", "budget_exhausted"].includes(run.status)) {
    const extra = h("input", { type: "number", min: 0, max: 200, value: 10, "aria-label": "Extra model calls" });
    const retry = h("button", { class: "primary", onclick: () => guarded(slot, retry, async () => {
      await api.retry(run.id, { extra_llm_calls: Number(extra.value) });
      await refresh();
    }) }, `Resume from ${run.phase}`);
    return h("section", { class: "panel" }, run.state.error ? errorBox(new Error(run.state.error)) : null, slot,
      h("div", { class: "row" }, field("Extra model calls", extra), retry));
  }
  if (run.status === "awaiting_user") {
    const answer = h("input", { size: 60, "aria-label": "Answer" });
    const send = h("button", { class: "primary", onclick: () => guarded(slot, send, async () => {
      await api.clarify(run.id, { answer: answer.value });
      await refresh();
    }) }, "Answer and resume");
    const questions = run.state.artifacts?.intake?.ambiguities || [];
    return h("section", { class: "panel" }, h("h2", {}, "The agent needs an answer"), h("ul", {}, questions.map((q) => h("li", {}, q))), slot, h("div", { class: "row" }, answer, send));
  }
  return null;
}

async function impactPanels(run) {
  const handle = run.state.impact?.handle;
  if (!handle) return null;
  try {
    return reportPanels(await api.impactReport(handle), run.snapshot_id);
  } catch (error) {
    return errorBox(error);
  }
}

export async function runDetailView(id) {
  const root = h("div", {});
  let events = [];
  let lastSeq = 0;
  let timer = null;
  let cancelled = false;
  let impactHandle = null;
  const impactSlot = h("div", {});
  const body = h("div", {});

  async function refresh() {
    const run = await api.run(id, lastSeq);
    events = events.concat(run.events);
    if (events.length) lastSeq = events[events.length - 1].seq;
    if (run.state.impact?.handle && run.state.impact.handle !== impactHandle) {
      impactHandle = run.state.impact.handle;
      const panels = await impactPanels(run);
      impactSlot.replaceChildren(h("h2", {}, "Impact analysis"), panels);
    }
    body.replaceChildren(
      h("h1", {}, `Run ${run.id} `, badge(run.status), " ", h("span", { class: "small muted" }, `tools ${run.config}, ${run.mode}`)),
      h("section", { class: "panel" }, h("p", {}, run.request), timeline(run)),
      actionPanel(run, refresh) || "",
      budgetPanel(run),
      approvalPanel(run, refresh) || "",
      verificationPanel(run) || "",
      reportPanel(run) || "",
      patchesPanel(run) || "",
      eventLog(events));
    clearTimeout(timer);
    if (!cancelled && ACTIVE.has(run.status)) timer = setTimeout(() => refresh().catch((e) => body.prepend(errorBox(e))), POLL_MS);
  }
  await refresh();
  root.append(body, impactSlot);
  return { el: root, cancel: () => { cancelled = true; clearTimeout(timer); } };
}
