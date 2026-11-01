import { h } from "./dom.js";

const css = (name) => getComputedStyle(document.documentElement).getPropertyValue(name).trim();

// Draws a witness path (PathStep[]: {edge, type, src, dst, tier}) as a small left-to-right graph.
export function derivationGraph(path) {
  const canvas = h("div", { id: "graph-canvas", role: "img", "aria-label": "Derivation path" });
  const summary = h("ol", { class: "small muted" }, path.map((p) => h("li", {}, `${p.src} -[${p.type}, ${p.tier}]-> ${p.dst}`)));
  const wrapper = h("div", {}, canvas, summary);
  if (!path.length) return h("p", { class: "muted" }, "This finding is a direct consequence, with no intermediate path.");
  queueMicrotask(() => {
    if (typeof cytoscape !== "function") return;
    const ids = [...new Set(path.flatMap((p) => [p.src, p.dst]))];
    cytoscape({
      container: canvas,
      elements: [
        ...ids.map((id) => ({ data: { id, label: id } })),
        ...path.map((p, i) => ({ data: { id: `e${i}`, source: p.src, target: p.dst, label: p.type } })),
      ],
      layout: { name: "breadthfirst", directed: true, spacingFactor: 1.1, padding: 24 },
      style: [
        { selector: "node", style: { label: "data(label)", "font-size": 10, color: css("--ink"), "background-color": css("--accent"), width: 14, height: 14, "text-wrap": "ellipsis", "text-max-width": 220, "text-valign": "bottom", "text-margin-y": 4 } },
        { selector: "edge", style: { label: "data(label)", "font-size": 9, color: css("--muted"), "line-color": css("--line"), "target-arrow-color": css("--muted"), "target-arrow-shape": "triangle", "curve-style": "bezier", "text-background-color": css("--panel"), "text-background-opacity": 1, "text-background-padding": 2 } },
      ],
      userPanningEnabled: true,
    });
  });
  return wrapper;
}
