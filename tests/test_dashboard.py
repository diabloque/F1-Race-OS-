from fastapi.testclient import TestClient

from raceos.api import create_app


def test_dashboard_homepage_assets_and_api_share_one_server(tmp_path):
    frontend = tmp_path / "dist"
    assets = frontend / "assets"
    assets.mkdir(parents=True)
    (frontend / "index.html").write_text(
        '<html><title>RaceOS</title><div id="root"></div></html>'
    )
    (frontend / "favicon.svg").write_text('<svg xmlns="http://www.w3.org/2000/svg"/>')
    (assets / "app.js").write_text("window.raceos = true;")
    with TestClient(create_app(tmp_path / "archive.sqlite3", frontend)) as client:
        response = client.get("/")
        assert response.status_code == 200
        assert 'id="root"' in response.text
        assert response.headers["cache-control"] == "no-cache"
        assert client.get("/assets/app.js").status_code == 200
        assert client.get("/favicon.svg").status_code == 200
        assert client.get("/api/sessions").json()["items"] == []
        assert client.get("/docs").status_code == 200
        assert client.get("/api/not-an-endpoint").status_code == 404


def test_missing_build_explains_setup_instead_of_returning_an_unassigned_homepage(
    tmp_path,
):
    with TestClient(
        create_app(tmp_path / "archive.sqlite3", tmp_path / "missing")
    ) as client:
        response = client.get("/")
        assert response.status_code == 503
        assert "npm run build" in response.text
        assert client.get("/docs").status_code == 200
