from tracegraph.ontology.types.code import register_code_edges, register_code_nodes
from tracegraph.ontology.types.data import register_data_edges, register_data_nodes
from tracegraph.ontology.types.governance import register_governance_edges, register_governance_nodes
from tracegraph.ontology.types.interface import register_interface_edges, register_interface_nodes
from tracegraph.ontology.types.verification import register_verification_edges, register_verification_nodes

__all__ = [
    "register_code_edges",
    "register_code_nodes",
    "register_data_edges",
    "register_data_nodes",
    "register_governance_edges",
    "register_governance_nodes",
    "register_interface_edges",
    "register_interface_nodes",
    "register_verification_edges",
    "register_verification_nodes",
]
