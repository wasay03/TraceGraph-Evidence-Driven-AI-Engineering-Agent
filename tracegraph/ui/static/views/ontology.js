import { api } from "../api.js";
import { badge, h, table } from "../dom.js";

export async function ontologyView() {
  const ontology = await api.ontology();
  return h("div", {},
    h("h1", {}, `Ontology ${ontology.semver} `, badge(ontology.catalog_in_sync ? "in sync" : "not synced", ontology.catalog_in_sync ? "passed" : "failed")),
    h("section", { class: "panel" }, h("h2", {}, `Node types (${ontology.node_types.length})`), table([
      { title: "Type", key: "name" }, { title: "Parent", key: "parent" },
      { title: "Natural key", class: "mono", key: "key" }, { title: "Owner", key: "owner" },
      { title: "Properties", class: "small", render: (t) => t.props.map((p) => p.name).join(", ") },
    ], ontology.node_types)),
    h("section", { class: "panel" }, h("h2", {}, `Edge types (${ontology.edge_types.length})`), table([
      { title: "Edge", key: "name" }, { title: "Inverse", key: "inverse" }, { title: "Card.", key: "cardinality" },
      { title: "Signatures", class: "small", render: (e) => e.signatures.map(([d, r]) => `${d} -> ${r}`).join(", ") },
      { title: "Tiers", class: "small", render: (e) => e.tiers.join(", ") },
    ], ontology.edge_types)));
}
