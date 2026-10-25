import socket
import uuid
from concurrent.futures import ThreadPoolExecutor
from functools import partial
from pathlib import Path
from threading import Barrier
from unittest.mock import Mock

import pytest
from alembic import command, op
from alembic.config import Config
from fastapi.testclient import TestClient
from sqlalchemy import event, func, inspect, select
from sqlalchemy.orm import Session
from test_database_integration import migrate
from test_requests import SETTINGS, confirmed_body

from deploy_buddy.db.config import DatabaseSafetyError
from deploy_buddy.db.models import DeploymentOperation, DeploymentRun, StatusEvent
from deploy_buddy.db.session import request_session
from deploy_buddy.main import app

pytestmark = pytest.mark.integration


@pytest.fixture
def database_client(monkeypatch, empty_database):
    migrate(monkeypatch, empty_database)
    app.dependency_overrides[request_session] = lambda: partial(Session, empty_database)
    try:
        with TestClient(app) as client:
            yield client, empty_database
    finally:
        app.dependency_overrides.clear()


def counts(engine):
    with Session(engine) as session:
        return tuple(
            session.scalar(select(func.count()).select_from(model))
            for model in (DeploymentRun, DeploymentOperation, StatusEvent)
        )


def test_confirmed_request_persists_and_status_is_auditable(database_client):
    client, engine = database_client
    body = confirmed_body(client)
    response = client.post("/requests", json=body)
    assert response.status_code == 201
    result = response.json()
    assert result["status"] == "planned"
    assert result["mode"] == "dry_run"
    assert result["confirmed_at"]
    assert result["plan_digest"] == body["plan_digest"]
    assert result["operations"][0]["settings"]["repository_url"] == SETTINGS["repository_url"]
    assert [(e["from_status"], e["to_status"]) for e in result["events"]] == [
        (None, "queued"),
        ("queued", "planned"),
    ]
    assert client.get(response.headers["Location"]).json() == result
    assert counts(engine) == (1, 1, 2)
    with Session(engine) as session:
        run = session.get(DeploymentRun, uuid.UUID(result["id"]))
        assert run.submission_started_at is None
        assert run.provider_service_id is None
        assert run.provider_deployment_id is None
        assert run.attempt_count == 0
        assert run.lease_owner is None
        assert session.scalar(select(StatusEvent).order_by(StatusEvent.id)).details == {
            "plan_digest": body["plan_digest"],
            "confirmed": True,
        }
    assert "idempotency_key" not in result
    assert client.get(f"/requests/{uuid.uuid4()}").status_code == 404


def test_duplicate_submission_returns_same_request_without_new_events(database_client):
    client, engine = database_client
    body = confirmed_body(client)
    first = client.post("/requests", json=body)
    second = client.post("/requests", json=body)
    assert (first.status_code, second.status_code) == (201, 200)
    assert first.json() == second.json()
    assert counts(engine) == (1, 1, 2)


def test_concurrent_duplicate_submissions_are_atomic(database_client):
    client, engine = database_client
    body = confirmed_body(client)
    barrier = Barrier(2)

    def submit():
        barrier.wait(timeout=5)
        return client.post("/requests", json=body)

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(lambda _: submit(), range(2)))
    assert sorted(result.status_code for result in results) == [200, 201]
    assert results[0].json() == results[1].json()
    assert counts(engine) == (1, 1, 2)


def test_reusing_key_for_different_proposal_is_a_conflict(database_client):
    client, engine = database_client
    original = confirmed_body(client)
    assert client.post("/requests", json=original).status_code == 201
    different = confirmed_body(client, service_name="different-service")
    different["idempotency_key"] = original["idempotency_key"]
    assert client.post("/requests", json=different).status_code == 409
    assert counts(engine) == (1, 1, 2)


def test_edit_after_preview_requires_fresh_confirmation(database_client):
    client, engine = database_client
    body = confirmed_body(client)
    body["service_name"] = "changed-service"
    assert client.post("/requests", json=body).status_code == 409
    assert counts(engine) == (0, 0, 0)


@pytest.mark.parametrize("failed_table", ["deployment_operations", "status_events"])
def test_transaction_rolls_back_request_operation_and_events(database_client, failed_table):
    client, engine = database_client
    body = confirmed_body(client)

    def interrupt(connection, cursor, statement, parameters, context, executemany):
        if statement.startswith(f"INSERT INTO {failed_table}"):
            raise RuntimeError("Simulated interruption")

    event.listen(engine, "before_cursor_execute", interrupt)
    try:
        with pytest.raises(RuntimeError, match="Simulated interruption"):
            client.post("/requests", json=body)
    finally:
        event.remove(engine, "before_cursor_execute", interrupt)
    assert counts(engine) == (0, 0, 0)
    # The same key can be retried after the rolled-back transaction.
    assert client.post("/requests", json=body).status_code == 201
    assert counts(engine) == (1, 1, 2)


def test_dry_run_contacts_only_local_postgresql(database_client, monkeypatch):
    client, engine = database_client
    # psycopg uses libpq, not Python sockets. Any Python HTTP/provider call is forbidden.
    outbound = Mock(side_effect=AssertionError("External integration attempted"))
    monkeypatch.setattr(socket, "create_connection", outbound)
    monkeypatch.setattr(socket.socket, "connect", outbound)
    monkeypatch.setenv("RENDER_API_KEY", "SECRET-never-read")
    monkeypatch.setenv("GITHUB_TOKEN", "SECRET-never-read")
    body = confirmed_body(client)
    response = client.post("/requests", json=body)
    assert response.status_code == 201
    assert client.get(response.headers["Location"]).status_code == 200
    assert "SECRET" not in response.text
    outbound.assert_not_called()
    assert counts(engine) == (1, 1, 2)


def test_upgrade_from_milestone_one_preserves_existing_data(monkeypatch, empty_database):
    monkeypatch.setenv("DATABASE_URL", empty_database.url.render_as_string(hide_password=False))
    config = Config(str(Path(__file__).resolve().parents[1] / "alembic.ini"))
    command.upgrade(config, "0001_local_foundation")
    with empty_database.begin() as connection:
        # Use frozen v1 columns: current ORM includes the new proposal digest.
        run_id = uuid.uuid4()
        connection.execute(
            DeploymentRun.__table__.insert().values(
                id=run_id, idempotency_key=uuid.uuid4(), **SETTINGS
            )
        )
    migrate(monkeypatch, empty_database)
    with Session(empty_database) as session:
        assert session.get(DeploymentRun, run_id).repository_url == SETTINGS["repository_url"]


def test_failed_upgrade_rolls_back_new_column_and_table(monkeypatch, empty_database):
    monkeypatch.setenv("DATABASE_URL", empty_database.url.render_as_string(hide_password=False))
    config = Config(str(Path(__file__).resolve().parents[1] / "alembic.ini"))
    command.upgrade(config, "0001_local_foundation")
    original = op.create_table

    def interrupted(name, *args, **kwargs):
        if name == "deployment_operations":
            raise RuntimeError("Simulated upgrade interruption")
        return original(name, *args, **kwargs)

    with monkeypatch.context() as patch:
        patch.setattr(op, "create_table", interrupted)
        with pytest.raises(RuntimeError, match="Simulated upgrade interruption"):
            migrate(patch, empty_database)
    assert "plan_digest" not in {
        c["name"] for c in inspect(empty_database).get_columns("deployment_runs")
    }
    assert "deployment_operations" not in inspect(empty_database).get_table_names()
    migrate(monkeypatch, empty_database)


@pytest.mark.parametrize(
    "ddl",
    [
        "CREATE TABLE unrelated_data (id integer)",
        "CREATE SCHEMA unrelated",
        "CREATE TYPE unexpected_kind AS ENUM ('unrelated')",
        "CREATE FUNCTION unexpected() RETURNS integer LANGUAGE SQL AS 'SELECT 1'",
        "ALTER TABLE deployment_runs ADD COLUMN unexpected integer",
        "UPDATE alembic_version SET version_num = 'unknown_revision'",
    ],
)
def test_upgrade_refuses_altered_or_unrelated_managed_schema(monkeypatch, empty_database, ddl):
    migrate(monkeypatch, empty_database)
    from sqlalchemy import text

    with empty_database.begin() as connection:
        connection.execute(text(ddl))
    try:
        with pytest.raises(DatabaseSafetyError, match="Migration refused"):
            migrate(monkeypatch, empty_database)
        # Refusal never removes unrelated data or definitions.
        if "TABLE unrelated_data" in ddl:
            assert "unrelated_data" in inspect(empty_database).get_table_names()
    finally:
        if "SCHEMA unrelated" in ddl:
            with empty_database.begin() as connection:
                connection.execute(text("DROP SCHEMA unrelated"))
