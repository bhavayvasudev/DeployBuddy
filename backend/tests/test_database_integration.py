import uuid
from pathlib import Path

import pytest
from alembic import command, op
from alembic.autogenerate import compare_metadata
from alembic.config import Config
from alembic.migration import MigrationContext
from sqlalchemy import inspect, select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from deploy_buddy.db.config import DatabaseSafetyError
from deploy_buddy.db.models import Base, DeploymentRun, LogRecord, RunStatus, StatusEvent
from deploy_buddy.db.safety import assert_empty_dedicated_database

pytestmark = pytest.mark.integration


def migrate(monkeypatch, engine):
    monkeypatch.setenv("DATABASE_URL", engine.url.render_as_string(hide_password=False))
    command.upgrade(Config(str(Path(__file__).resolve().parents[1] / "alembic.ini")), "head")


def test_empty_database_migrates_and_matches_models(monkeypatch, empty_database):
    with empty_database.connect() as connection:
        assert_empty_dedicated_database(connection)
    migrate(monkeypatch, empty_database)
    assert set(inspect(empty_database).get_table_names()) == {
        "alembic_version",
        "deployment_runs",
        "status_events",
        "log_records",
        "deployment_operations",
    }
    with empty_database.connect() as connection:
        assert compare_metadata(MigrationContext.configure(connection), Base.metadata) == []


def test_run_event_and_log_persist_atomically(monkeypatch, empty_database):
    migrate(monkeypatch, empty_database)
    with Session(empty_database) as session, session.begin():
        run = DeploymentRun(
            idempotency_key=uuid.uuid4(),
            repository_url="https://github.com/example/service",
            service_name="local-service",
            build_command="npm ci && npm run build",
            start_command="npm start",
        )
        session.add(run)
        session.flush()
        run_id = run.id
        session.add(
            StatusEvent(run_id=run_id, to_status=RunStatus.QUEUED, message="Created locally")
        )
        session.add(LogRecord(run_id=run_id, level="info", message="No provider called"))
    with Session(empty_database) as session:
        stored = session.get(DeploymentRun, run_id)
        assert stored.status == RunStatus.QUEUED
        assert stored.mode == "dry_run"
        assert stored.created_at.tzinfo is not None
        assert stored.submission_started_at is None
        assert session.scalar(select(StatusEvent)).run_id == run_id
        assert session.scalar(select(LogRecord)).run_id == run_id


@pytest.mark.parametrize(
    "ddl",
    [
        "CREATE TABLE existing_data (id integer)",
        "CREATE SCHEMA unrelated",
        "CREATE TYPE existing_kind AS ENUM ('original')",
        "CREATE FUNCTION existing_function() RETURNS integer LANGUAGE SQL AS 'SELECT 1'",
    ],
)
def test_migration_refuses_nonempty_database_without_modifying_it(
    monkeypatch,
    empty_database,
    ddl,
):
    with empty_database.begin() as connection:
        connection.execute(text(ddl))
    try:
        with pytest.raises(DatabaseSafetyError, match="not empty"):
            migrate(monkeypatch, empty_database)
        assert "deployment_runs" not in inspect(empty_database).get_table_names()
        if "TABLE" in ddl:
            assert "existing_data" in inspect(empty_database).get_table_names()
        elif "SCHEMA" in ddl:
            assert "unrelated" in inspect(empty_database).get_schema_names()
        elif "TYPE" in ddl:
            assert "existing_kind" in {kind["name"] for kind in inspect(empty_database).get_enums()}
        else:
            with empty_database.connect() as connection:
                assert connection.scalar(text("SELECT existing_function()")) == 1
    finally:
        if "SCHEMA" in ddl:
            with empty_database.begin() as connection:
                connection.execute(text("DROP SCHEMA unrelated"))


def test_repeat_upgrade_is_safe_noop(monkeypatch, empty_database):
    migrate(monkeypatch, empty_database)
    migrate(monkeypatch, empty_database)


def test_partial_lease_and_invalid_status_are_rejected(monkeypatch, empty_database):
    migrate(monkeypatch, empty_database)
    for field, value in [("lease_owner", "worker-a"), ("status", "invented")]:
        with Session(empty_database) as session:
            run = DeploymentRun(
                idempotency_key=uuid.uuid4(),
                repository_url="https://github.com/example/service",
                service_name="service",
                build_command="npm ci",
                start_command="npm start",
            )
            setattr(run, field, value)
            session.add(run)
            with pytest.raises(IntegrityError):
                session.commit()


def test_failed_initial_migration_rolls_back_all_ddl(monkeypatch, empty_database):
    original_create_table = op.create_table

    def interrupted_create_table(name, *args, **kwargs):
        if name == "status_events":
            raise RuntimeError("Simulated interruption after the first table")
        return original_create_table(name, *args, **kwargs)

    with monkeypatch.context() as patch:
        patch.setattr(op, "create_table", interrupted_create_table)
        with pytest.raises(RuntimeError, match="Simulated interruption"):
            migrate(patch, empty_database)
    assert inspect(empty_database).get_table_names() == []
    migrate(monkeypatch, empty_database)


def test_idempotency_key_is_unique(monkeypatch, empty_database):
    migrate(monkeypatch, empty_database)
    key = uuid.uuid4()
    for attempt in range(2):
        with Session(empty_database) as session:
            session.add(
                DeploymentRun(
                    idempotency_key=key,
                    repository_url="https://github.com/example/service",
                    service_name="service",
                    build_command="npm ci",
                    start_command="npm start",
                )
            )
            if attempt == 0:
                session.commit()
            else:
                with pytest.raises(IntegrityError):
                    session.commit()
