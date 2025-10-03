import pytest
from fastapi.testclient import TestClient

from app.extensions import local_queue_extension
from app.main import app


@pytest.fixture
def client(tmp_path):
    old_data_dir = local_queue_extension.data_dir
    old_jobs_dir = local_queue_extension.jobs_dir
    local_queue_extension.data_dir = tmp_path
    local_queue_extension.jobs_dir = tmp_path / "jobs"
    local_queue_extension.jobs_dir.mkdir(parents=True, exist_ok=True)
    local_queue_extension.clear()

    with TestClient(app) as test_client:
        yield test_client

    local_queue_extension.clear()
    local_queue_extension.data_dir = old_data_dir
    local_queue_extension.jobs_dir = old_jobs_dir


def test_local_queue_endpoints_exposed(client):
    response = client.post("/local/queue/html", json={"html": "<p>Hello</p>"})
    assert response.status_code == 200
    payload = response.json()
    assert "job_id" in payload
    assert payload["job_id"]
    assert payload["status_url"].endswith(payload["job_id"])

    status_response = client.get(f"/local/job/{payload['job_id']}")
    assert status_response.status_code == 200
    status_payload = status_response.json()
    assert status_payload["status"] == "queued"


def test_docs_conversion_endpoints(client):
    html_response = client.post("/parse/docs/html", json={"html": "<h1>Hi</h1>"})
    assert html_response.status_code == 200
    html_payload = html_response.json()
    assert "requests" in html_payload
    assert isinstance(html_payload["requests"], list)

    markdown_response = client.post("/parse/docs/markdown", json={"markdown": "# Title"})
    assert markdown_response.status_code == 200
    markdown_payload = markdown_response.json()
    assert "requests" in markdown_payload
    assert isinstance(markdown_payload["requests"], list)
