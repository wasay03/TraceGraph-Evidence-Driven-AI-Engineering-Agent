from httpx import AsyncClient


async def test_ui_is_served_without_a_key(client: AsyncClient) -> None:
    root = await client.get("/")
    assert root.status_code == 307 and root.headers["location"] == "/ui/"
    page = await client.get("/ui/")
    assert page.status_code == 200 and "TraceGraph" in page.text
    for asset in ("app.js", "api.js", "views/runs.js", "styles.css", "vendor/cytoscape.min.js"):
        assert (await client.get(f"/ui/{asset}")).status_code == 200


async def test_health_reports_database_ok(client: AsyncClient) -> None:
    response = await client.get("/health")
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"
    assert body["database"] == "ok"
    assert response.headers["X-Request-ID"]
