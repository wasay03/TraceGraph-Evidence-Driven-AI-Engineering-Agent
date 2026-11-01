from pathlib import Path

from httpx import AsyncClient

from tests.conftest import commit_all
from tracegraph.config import Settings
from tracegraph.core import Database
from tracegraph.workers import IndexWorker


async def _index(client: AsyncClient, headers: dict, settings: Settings, repo_id: int, kind: str) -> dict:
    accepted = await client.post(f"/repos/{repo_id}/snapshots", json={"kind": kind}, headers=headers)
    assert accepted.status_code == 202, accepted.text
    database = Database(settings)
    try:
        assert await IndexWorker(database, settings, "test-worker").run_once() is True
    finally:
        await database.dispose()
    return (await client.get(f"/snapshots/{accepted.json()['snapshot']['id']}", headers=headers)).json()


def _counts(snapshot: dict) -> dict[tuple[str, str], int]:
    return {(c["kind"], c["type_name"]): c["total"] for c in snapshot["counts"]}


async def test_full_then_incremental_index(client: AsyncClient, auth_headers, settings: Settings, shop_repo: Path):
    repo = (await client.post("/repos", json={"url": str(shop_repo)}, headers=auth_headers)).json()

    first = await _index(client, auth_headers, settings, repo["id"], "full")
    assert first["status"] == "ready", first["error"]
    counts = _counts(first)
    assert counts[("node", "Module")] >= 8 and counts[("edge", "CALLS")] > 5
    assert first["stats"]["nodes"] > 50 and first["extractor_versions"]["structure"]
    assert any(h["kind"] == "dynamic_attribute" for h in first["coverage_holes"])
    validation = (await client.get(f"/snapshots/{first['id']}/validation", headers=auth_headers)).json()
    assert validation["valid"] is True, validation["violations"][:5]

    services = shop_repo / "app" / "services.py"
    services.write_text(services.read_text().replace("def describe_status(", "def describe_order_status(")
                        .replace("return \"unknown\"", "return \"unknown status\""))
    api = shop_repo / "app" / "api.py"
    api.write_text(api.read_text().replace("describe_status", "describe_order_status"))
    commit_all(shop_repo, "rename describe_status")

    second = await _index(client, auth_headers, settings, repo["id"], "incremental")
    assert second["status"] == "ready", second["error"]
    assert second["stats"]["base_seq"] == first["seq"]
    assert second["stats"]["scope_files"] == 3  # services.py, api.py + tests/test_orders.py (imports services)
    assert _counts(second)[("node", "Function")] == counts[("node", "Function")]
    validation = (await client.get(f"/snapshots/{second['id']}/validation", headers=auth_headers)).json()
    assert validation["valid"] is True, validation["violations"][:5]


async def test_failed_job_marks_snapshot_failed(client: AsyncClient, auth_headers, settings: Settings,
                                                shop_repo: Path):
    repo = (await client.post("/repos", json={"url": str(shop_repo)}, headers=auth_headers)).json()
    accepted = (await client.post(f"/repos/{repo['id']}/snapshots", json={}, headers=auth_headers)).json()
    (shop_repo / ".git").rename(shop_repo / ".git-gone")
    database = Database(settings)
    try:
        assert await IndexWorker(database, settings, "test-worker").run_once() is True
    finally:
        await database.dispose()
        (shop_repo / ".git-gone").rename(shop_repo / ".git")
    snapshot = (await client.get(f"/snapshots/{accepted['snapshot']['id']}", headers=auth_headers)).json()
    assert snapshot["status"] == "failed" and "git archive" in snapshot["error"]
    assert snapshot["counts"] == []
