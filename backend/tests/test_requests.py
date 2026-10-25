import socket
import uuid
from unittest.mock import Mock

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.exc import OperationalError

from deploy_buddy.db.session import request_session
from deploy_buddy.main import app
from deploy_buddy.providers.boundary import ExternalIntegrationDisabled, invoke_external

SETTINGS = {
    "repository_url": "https://github.com/example/service",
    "service_name": "test-service",
    "build_command": "npm ci && npm run build",
    "start_command": "npm start",
}


@pytest.fixture
def client():
    with TestClient(app) as client:
        yield client


def confirmed_body(client, **changes):
    settings = {**SETTINGS, **changes}
    preview = client.post("/requests/preview", json=settings)
    assert preview.status_code == 200
    return {
        **settings,
        "idempotency_key": str(uuid.uuid4()),
        "confirmed": True,
        "plan_digest": preview.json()["plan_digest"],
    }


@pytest.mark.parametrize(
    "url",
    [
        "http://github.com/owner/repo",
        "https://gitlab.com/owner/repo",
        "git@github.com:owner/repo.git",
        "ssh://github.com/owner/repo",
        "https://github.com.evil.test/owner/repo",
        "https://github.com@evil.test/owner/repo",
        "https://user:SECRET@github.com/owner/repo",
        "https://github.com:443/owner/repo",
        "https://github.com/owner/repo?token=SECRET",
        "https://github.com/owner/repo#SECRET",
        "https://github.com/owner/repo/tree/main",
        "https://github.com/owner",
        "https://github.com/owner/..",
        "https://github.com/owner/.git",
        "https://github.com/owner/%2e%2e",
        "https://github.com/owner/repo\\evil",
        "https://github.com/owner/repo\n",
        "https://github.com/-owner/repo",
        "https://github.com/owner--name/repo",
        "https://github.com/owner/repo/extra",
        "https://127.0.0.1/owner/repo",
        "https://github.com/öwner/repo",
    ],
)
def test_invalid_repository_urls(client, url, caplog):
    response = client.post("/requests/preview", json={**SETTINGS, "repository_url": url})
    assert response.status_code == 422
    assert "SECRET" not in response.text + caplog.text


@pytest.mark.parametrize(
    "changes",
    [
        {"service_name": ""},
        {"service_name": "UPPER"},
        {"service_name": "-leading"},
        {"service_name": "trailing-"},
        {"service_name": "a" * 64},
        {"runtime": "python"},
        {"service_type": "worker"},
        {"provider": "other"},
        {"mode": "live"},
        {"mode": None},
        {"build_command": "npm ci; curl https://evil.test"},
        {"build_command": "TOKEN=SECRET npm ci"},
        {"start_command": "node server.js"},
        {"env": {"TOKEN": "SECRET"}},
        {"services": [{}, {}]},
        {"render_token": "SECRET"},
        {"repository_url": 42},
    ],
)
def test_invalid_settings(client, changes, caplog):
    response = client.post("/requests/preview", json={**SETTINGS, **changes})
    assert response.status_code == 422
    assert "SECRET" not in response.text + caplog.text


@pytest.mark.parametrize("confirmation", [None, False, "true", 1, "yes"])
def test_missing_or_non_boolean_confirmation(client, confirmation):
    body = confirmed_body(client)
    if confirmation is None:
        body.pop("confirmed")
    else:
        body["confirmed"] = confirmation
    # Invalid input must fail without configuring or connecting to a database.
    assert client.post("/requests", json=body).status_code == 422


def test_invalid_uuid_and_missing_digest(client):
    body = confirmed_body(client)
    body["idempotency_key"] = "not-a-uuid"
    assert client.post("/requests", json=body).status_code == 422
    body = confirmed_body(client)
    body.pop("plan_digest")
    assert client.post("/requests", json=body).status_code == 422


def test_preview_is_offline_and_canonical(client, monkeypatch):
    network = Mock(side_effect=AssertionError("Outbound network is forbidden"))
    monkeypatch.setattr(socket, "create_connection", network)
    monkeypatch.setattr(socket.socket, "connect", network)
    response = client.post(
        "/requests/preview",
        json={**SETTINGS, "repository_url": "https://github.com/Example/Service.git/"},
    )
    assert response.status_code == 200
    preview = response.json()
    assert preview["settings"]["repository_url"] == SETTINGS["repository_url"]
    assert len(preview["operations"]) == 1
    assert "not verified offline" in preview["notice"]
    assert (
        preview["plan_digest"]
        == client.post("/requests/preview", json=SETTINGS).json()["plan_digest"]
    )
    network.assert_not_called()


@pytest.mark.parametrize("mode", ["dry_run", "live", "unknown", "", None])
def test_external_integration_fails_before_invoking_callback(mode):
    provider = Mock(side_effect=AssertionError("Provider must never run"))
    with pytest.raises(ExternalIntegrationDisabled):
        invoke_external(mode, provider, token="SECRET")
    provider.assert_not_called()


def test_database_errors_do_not_leak_secrets(client, caplog):
    def unavailable():
        raise OperationalError("SECRET statement", {"token": "SECRET"}, Exception("SECRET"))

    app.dependency_overrides[request_session] = lambda: unavailable
    try:
        response = client.post("/requests", json=confirmed_body(client))
    finally:
        app.dependency_overrides.clear()
    assert response.status_code == 503
    assert "SECRET" not in response.text + caplog.text


def test_execution_routes_remain_absent(client):
    assert client.post("/deployments", json={}).status_code == 404
    assert client.post("/requests/execute", json={}).status_code == 405


def test_malformed_json_never_echoes_secrets(client, caplog):
    response = client.post(
        "/requests/preview",
        content='{"token":"SECRET", broken}',
        headers={"Content-Type": "application/json"},
    )
    assert response.status_code == 422
    assert "SECRET" not in response.text + caplog.text
