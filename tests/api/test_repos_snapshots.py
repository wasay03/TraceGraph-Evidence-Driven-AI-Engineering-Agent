import subprocess
from pathlib import Path

from httpx import AsyncClient


def make_git_repo(path: Path) -> str:
    path.mkdir(parents=True, exist_ok=True)
    (path / "app.py").write_text("def f():\n    return 1\n")
    for cmd in (["init", "-q", "-b", "main"], ["add", "."], ["-c", "user.email=t@t", "-c", "user.name=t",
                                                          "commit", "-q", "-m", "init"]):
        subprocess.run(["git", "-C", str(path), *cmd], check=True)
    return subprocess.run(["git", "-C", str(path), "rev-parse", "HEAD"], check=True, capture_output=True,
                          text=True).stdout.strip()


async def test_requires_api_key(client: AsyncClient):
    assert (await client.get("/ontology")).status_code == 401
    assert (await client.get("/ontology", headers={"X-API-Key": "wrong"})).status_code == 401


async def test_ontology_sync_and_describe(client: AsyncClient, auth_headers):
    body = (await client.post("/ontology/sync", headers=auth_headers)).json()
    assert body["catalog_in_sync"] is True
    assert any(e["name"] == "CALLS" for e in body["edge_types"])


async def test_register_repo_and_request_snapshot(client: AsyncClient, auth_headers, tmp_path: Path):
    sha = make_git_repo(tmp_path / "r1")
    created = await client.post("/repos", json={"url": str(tmp_path / "r1")}, headers=auth_headers)
    assert created.status_code == 201, created.text
    repo = created.json()
    assert repo["url"].startswith("file://") and repo["name"] == "r1"

    dup = await client.post("/repos", json={"url": str(tmp_path / "r1")}, headers=auth_headers)
    assert dup.status_code == 409

    accepted = await client.post(f"/repos/{repo['id']}/snapshots", json={}, headers=auth_headers)
    assert accepted.status_code == 202, accepted.text
    snapshot = accepted.json()["snapshot"]
    assert snapshot["commit_sha"] == sha and snapshot["status"] == "pending" and snapshot["seq"] == 1

    detail = (await client.get(f"/snapshots/{snapshot['id']}", headers=auth_headers)).json()
    assert detail["counts"] == [] and detail["coverage_holes"] == []
    assert (await client.get("/snapshots/999999", headers=auth_headers)).status_code == 404


async def test_rejects_remote_and_bad_refs(client: AsyncClient, auth_headers, tmp_path: Path):
    remote = await client.post("/repos", json={"url": "https://github.com/x/y"}, headers=auth_headers)
    assert remote.status_code == 400
    make_git_repo(tmp_path / "r2")
    repo = (await client.post("/repos", json={"url": str(tmp_path / "r2")}, headers=auth_headers)).json()
    bad = await client.post(f"/repos/{repo['id']}/snapshots", json={"ref": "nope"}, headers=auth_headers)
    assert bad.status_code == 400
