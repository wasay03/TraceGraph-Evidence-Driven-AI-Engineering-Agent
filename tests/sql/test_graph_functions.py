import json
from collections.abc import Iterator

import psycopg
import pytest

from tests.conftest import TEST_DATABASE_URL

NODE_TYPES = [
    {"id": 1, "name": "Entity", "parent_id": None, "is_abstract": True, "natural_key": [], "tiers": [], "owner": None},
    {"id": 2, "name": "Function", "parent_id": 1, "is_abstract": False, "natural_key": ["{q}"],
     "tiers": ["asserted"], "owner": "t"},
    {"id": 3, "name": "Table", "parent_id": 1, "is_abstract": False, "natural_key": ["{q}"],
     "tiers": ["asserted"], "owner": "t"},
]
EDGE_TYPES = [{"id": 1, "name": "CALLS", "cardinality": "N:M", "inverse_name": "CALLED_BY", "flags": {},
               "tiers": ["asserted"], "evidence_policy": "span_required"},
              {"id": 2, "name": "HANDLED_BY", "cardinality": "N:1", "inverse_name": None, "flags": {},
               "tiers": ["asserted"], "evidence_policy": "span_required"}]
SIGNATURES = [{"edge_type_id": 1, "domain_type_id": 2, "range_type_id": 2},
              {"edge_type_id": 2, "domain_type_id": 2, "range_type_id": 2}]


def _node(node_id: int, key: str, path: str, lo: int = 1, type_id: int = 2) -> dict:
    return {"id": node_id, "type_id": type_id, "natural_key": key, "props": {"q": key}, "tier": "asserted",
            "file_path": path, "span_lo": lo, "span_hi": lo + 2}


def _edge(edge_id: int, src: int, dst: int, owner: str, type_id: int = 1) -> dict:
    return {"id": edge_id, "type_id": type_id, "src": src, "dst": dst, "props": {}, "tier": "asserted",
            "confidence": None, "owner_file": owner}


@pytest.fixture
def conn(migrated_db: str) -> Iterator[psycopg.Connection]:
    with psycopg.connect(TEST_DATABASE_URL.replace("+psycopg", "")) as connection:
        yield connection
        connection.rollback()


@pytest.fixture
def repo_id(conn: psycopg.Connection) -> int:
    catalog = {"node_types": NODE_TYPES, "edge_types": EDGE_TYPES, "signatures": SIGNATURES, "props": []}
    conn.execute("SELECT tg_ontology_sync(%s, %s::jsonb)", ("0.0.1-test", json.dumps(catalog)))
    return conn.execute("SELECT id FROM tg_repo_create('file:///t', 't', NULL)").fetchone()[0]


def _commit_nodes(conn, repo_id, seq, nodes, scope=None):
    return conn.execute("SELECT * FROM tg_node_commit(%s, %s, %s::jsonb, %s)",
                        (repo_id, seq, json.dumps(nodes), scope)).fetchone()


def _keys_at(conn, repo_id, seq):
    return sorted(r[0] for r in conn.execute("SELECT natural_key FROM tg_node_list_at(%s, %s)", (repo_id, seq)))


def test_node_commit_versions_rows(conn, repo_id):
    assert _commit_nodes(conn, repo_id, 1, [_node(1, "a", "a.py"), _node(2, "b", "b.py")]) == (2, 0)
    # unchanged a, moved b (span change), c added: b closed + reinserted, c inserted
    assert _commit_nodes(conn, repo_id, 2, [_node(1, "a", "a.py"), _node(2, "b", "b.py", lo=5),
                                            _node(3, "c", "c.py")]) == (2, 1)
    # full snapshot without a: a closed
    assert _commit_nodes(conn, repo_id, 3, [_node(2, "b", "b.py", lo=5), _node(3, "c", "c.py")]) == (0, 1)
    assert _keys_at(conn, repo_id, 1) == ["a", "b"]
    assert _keys_at(conn, repo_id, 2) == ["a", "b", "c"]
    assert _keys_at(conn, repo_id, 3) == ["b", "c"]


def test_scoped_commit_only_touches_scope_files(conn, repo_id):
    _commit_nodes(conn, repo_id, 1, [_node(1, "a", "a.py"), _node(2, "b", "b.py")])
    assert _commit_nodes(conn, repo_id, 2, [], scope=["b.py"]) == (0, 1)
    assert _keys_at(conn, repo_id, 2) == ["a"]


def test_validate_reports_dangling_signature_and_cardinality(conn, repo_id):
    _commit_nodes(conn, repo_id, 1, [_node(1, "f", "a.py"), _node(2, "g", "a.py"), _node(3, "h", "a.py"),
                                     _node(4, "orders", None, type_id=3)])
    edges = [_edge(10, 1, 2, "a.py"), _edge(11, 1, 99, "a.py"), _edge(12, 1, 4, "a.py"),
             _edge(13, 1, 2, "a.py", type_id=2), _edge(14, 1, 3, "a.py", type_id=2)]
    assert conn.execute("SELECT * FROM tg_edge_commit(%s, 1, %s::jsonb, NULL)",
                        (repo_id, json.dumps(edges))).fetchone() == (5, 0)
    violations = sorted(r[0] for r in conn.execute("SELECT * FROM tg_graph_validate(%s, 1)", (repo_id,)))
    assert violations == ["cardinality_violation", "dangling_endpoint", "signature_violation"]


def test_evidence_links_and_lookup(conn, repo_id):
    _commit_nodes(conn, repo_id, 1, [_node(1, "f", "a.py"), _node(2, "g", "a.py")])
    conn.execute("SELECT * FROM tg_edge_commit(%s, 1, %s::jsonb, NULL)", (repo_id, json.dumps([_edge(10, 1, 2, "a.py")])))
    ev = [{"id": 500, "extractor": "x", "extractor_version": "1", "method": "ast", "file_path": "a.py",
           "span_lo": 3, "span_hi": 4, "snippet_hash": "h", "commit_sha": "c", "confidence": None, "rationale": None}]
    conn.execute("SELECT * FROM tg_evidence_commit(%s, %s::jsonb, %s::jsonb, NULL)",
                 (repo_id, json.dumps(ev), json.dumps([{"edge_id": 10, "evidence_id": 500}])))
    rows = conn.execute("SELECT edge_id, file_path, line_start, line_end FROM tg_evidence_for_edges(%s, %s)",
                        (repo_id, [10])).fetchall()
    assert rows == [(10, "a.py", 3, 4)]


def test_repo_create_conflict_maps_to_tg409(conn, repo_id):
    with pytest.raises(psycopg.Error) as info:
        conn.execute("SELECT * FROM tg_repo_create('file:///t', 't', NULL)")
    assert info.value.sqlstate == "TG409"
