from fastapi.testclient import TestClient

from deploy_buddy.main import app


def test_liveness_without_database_or_provider():
    with TestClient(app) as client:
        response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok", "product": "deploy-buddy"}


def test_deployment_execution_is_not_exposed():
    with TestClient(app) as client:
        assert client.post("/deployments", json={}).status_code == 404
