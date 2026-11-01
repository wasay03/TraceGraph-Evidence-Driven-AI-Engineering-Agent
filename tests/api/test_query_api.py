from pathlib import Path

from httpx import AsyncClient

from tests.api.test_indexing_e2e import _index
from tracegraph.config import Settings

WRITES_STATUS = {
    "op": "reach",
    "input": {"op": "select", "type": "Endpoint"},
    "rpq": "HANDLED_BY . (CALLS|INJECTS)* . WRITES_TO",
    "target_types": ["Column"],
}


async def test_query_answer_roundtrip(client: AsyncClient, auth_headers, settings: Settings, shop_repo: Path):
    repo = (await client.post("/repos", json={"url": str(shop_repo)}, headers=auth_headers)).json()
    snapshot = await _index(client, auth_headers, settings, repo["id"], "full")

    response = await client.post("/query", json={"repo_id": repo["id"], "query": WRITES_STATUS}, headers=auth_headers)
    assert response.status_code == 200, response.text
    answer = response.json()
    assert answer["snapshot"]["seq"] == snapshot["seq"] and answer["truth"] == "ROWS"
    assert "orders.status" in {r["node"]["key"] for r in answer["rows"]}
    derivation = answer["derivations"][0]
    assert derivation["path"][0]["type"] == "HANDLED_BY"
    assert derivation["evidence"] and derivation["evidence"][0]["file"].startswith("app/")

    stored = await client.get(f"/answers/{answer['handle']}", headers=auth_headers)
    assert stored.status_code == 200 and stored.json()["rows"] == answer["rows"]
    assert (await client.get("/answers/ans_missing", headers=auth_headers)).status_code == 404


async def test_query_errors(client: AsyncClient, auth_headers, settings: Settings, shop_repo: Path):
    repo = (await client.post("/repos", json={"url": str(shop_repo)}, headers=auth_headers)).json()
    no_snapshot = await client.post("/query", json={"repo_id": repo["id"], "query": WRITES_STATUS}, headers=auth_headers)
    assert no_snapshot.status_code == 400
    await _index(client, auth_headers, settings, repo["id"], "full")
    bad_rpq = {**WRITES_STATUS, "rpq": "HANDLED_BY . NOPE"}
    typed = await client.post("/query", json={"repo_id": repo["id"], "query": bad_rpq}, headers=auth_headers)
    assert typed.status_code == 422 and typed.json()["error"]["code"] == "query_type_error"
    malformed = await client.post("/query", json={"repo_id": repo["id"], "query": {"op": "bogus"}}, headers=auth_headers)
    assert malformed.status_code == 422


async def test_source_endpoint_serves_lines_at_the_snapshot_commit(client: AsyncClient, auth_headers, settings: Settings,
                                                                   shop_repo: Path):
    repo = (await client.post("/repos", json={"url": str(shop_repo)}, headers=auth_headers)).json()
    snapshot = await _index(client, auth_headers, settings, repo["id"], "full")
    url = f"/snapshots/{snapshot['id']}/source"
    ok = await client.get(url, params={"path": "app/services.py", "start": 1, "end": 2}, headers=auth_headers)
    assert ok.status_code == 200 and ok.json()["lines"][0].startswith("from app.models")
    escape = await client.get(url, params={"path": "../secret", "start": 1}, headers=auth_headers)
    assert escape.status_code == 400
    missing = await client.get(url, params={"path": "app/nope.py", "start": 1}, headers=auth_headers)
    assert missing.status_code == 404
