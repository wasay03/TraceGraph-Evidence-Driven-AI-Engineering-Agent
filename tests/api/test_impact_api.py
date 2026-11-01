from pathlib import Path

from httpx import AsyncClient

from tests.api.test_indexing_e2e import _index
from tracegraph.config import Settings


async def test_impact_and_invariants(client: AsyncClient, auth_headers, settings: Settings, shop_repo: Path):
    repo = (await client.post("/repos", json={"url": str(shop_repo)}, headers=auth_headers)).json()
    await _index(client, auth_headers, settings, repo["id"], "full")

    body = {"repo_id": repo["id"], "changes": [{"kind": "make_column_nullable", "column": "orders.discount_code"}]}
    response = await client.post("/impact", json=body, headers=auth_headers)
    assert response.status_code == 200, response.text
    report = response.json()
    assert report["overlay"] and report["handle"].startswith("ans_")
    assert report["summary"]["BREAKS"] == 1
    breaks = next(f for f in report["findings"] if f["cls"] == "BREAKS")
    assert breaks["node"]["key"] == "app.services.calculate_total"
    assert breaks["evidence"] and breaks["evidence"][-1]["file"] == "app/services.py"

    stored = await client.get(f"/impact/{report['handle']}", headers=auth_headers)
    assert stored.status_code == 200 and stored.json()["findings"] == report["findings"]

    bad = {"repo_id": repo["id"], "changes": [{"kind": "make_column_nullable", "column": "orders.missing"}]}
    assert (await client.post("/impact", json=bad, headers=auth_headers)).status_code == 422

    checked = await client.post("/invariants/check", json={"repo_id": repo["id"], "invariants": ["INV-004"]},
                                headers=auth_headers)
    assert checked.status_code == 200
    assert checked.json()["truth"] == "FALSE"
    assert [v["node"]["key"] for v in checked.json()["violations"]] == ["tenants.name"]
