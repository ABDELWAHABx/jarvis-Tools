from fastapi.testclient import TestClient

from app.main import app


def test_studio_respects_root_path_for_assets_and_links():
    client = TestClient(app, root_path="/tools")

    response = client.get("/")

    assert response.status_code == 200
    html = response.text

    assert 'href="/tools/static/css/studio.css"' in html
    assert 'src="/tools/static/js/studio.js"' in html
    assert 'href="/tools/docs"' in html
    assert 'openapiUrl: "/tools/openapi.json"' in html
