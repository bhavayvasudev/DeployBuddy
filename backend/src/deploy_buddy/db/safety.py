from sqlalchemy import Connection, inspect, text

from deploy_buddy.db.config import ALLOWED_DATABASES, DatabaseSafetyError


def assert_dedicated_identity(connection: Connection) -> None:
    identity = (
        connection.execute(
            text(
                "SELECT current_database() AS name, current_user AS role, "
                "pg_get_userbyid(datdba) AS owner FROM pg_database "
                "WHERE datname = current_database()"
            )
        )
        .mappings()
        .one()
    )
    if (
        identity["name"] not in ALLOWED_DATABASES
        or identity["role"] != "deploy_buddy"
        or identity["owner"] != "deploy_buddy"
    ):
        raise DatabaseSafetyError("Connected database and owner are not dedicated to Deploy Buddy.")


def assert_empty_dedicated_database(connection: Connection) -> None:
    """Verify the server's actual database and role, then all non-system schemas."""
    assert_dedicated_identity(connection)
    count = connection.scalar(
        text(
            "SELECT count(*) FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace "
            "WHERE n.nspname !~ '^pg_' AND n.nspname <> 'information_schema' "
            "AND c.relkind IN ('r', 'p', 'v', 'm', 'S', 'f')"
        )
    )
    foreign_schemas = connection.scalar(
        text(
            "SELECT count(*) FROM pg_namespace WHERE nspname !~ '^pg_' "
            "AND nspname NOT IN ('information_schema', 'public')"
        )
    )
    user_definitions = connection.scalar(
        text(
            "SELECT count(*) FROM ("
            "SELECT t.typnamespace AS namespace FROM pg_type t UNION ALL "
            "SELECT p.pronamespace AS namespace FROM pg_proc p"
            ") objects JOIN pg_namespace n ON n.oid = objects.namespace "
            "WHERE n.nspname !~ '^pg_' AND n.nspname <> 'information_schema'"
        )
    )
    if count or foreign_schemas or user_definitions:
        raise DatabaseSafetyError("Initial migration refused: database is not empty.")


def assert_migration_target(connection: Connection) -> None:
    """Allow bootstrap or a recognized, dedicated product schema; never adopt other data."""
    inspector = inspect(connection)
    if "alembic_version" not in inspector.get_table_names(schema="public"):
        assert_empty_dedicated_database(connection)
        return
    assert_dedicated_identity(connection)
    versions = connection.scalars(text("SELECT version_num FROM public.alembic_version")).all()
    if versions not in (["0001_local_foundation"], ["0002_dry_run_requests"]):
        raise DatabaseSafetyError("Migration refused: unrecognized managed schema revision.")
    # Frozen identity of the original schema, independent of mutable ORM metadata.
    expected = {
        "alembic_version": {"version_num"},
        "deployment_runs": set(
            "id idempotency_key repository_url service_name build_command start_command provider "
            "mode status confirmed_at created_at updated_at attempt_count lease_owner lease_token "
            "lease_expires_at deadline_at submission_started_at provider_service_id "
            "provider_deployment_id deployed_url".split()
        ),
        "status_events": set("id run_id from_status to_status message details created_at".split()),
        "log_records": set("id run_id level message created_at".split()),
    }
    if versions == ["0002_dry_run_requests"]:
        expected["deployment_runs"].add("plan_digest")
        expected["deployment_operations"] = set(
            "id run_id sequence kind status specification created_at".split()
        )
    tables = set(inspector.get_table_names(schema="public"))
    if tables != set(expected) or any(
        {column["name"] for column in inspector.get_columns(table, schema="public")} != columns
        for table, columns in expected.items()
    ):
        raise DatabaseSafetyError("Migration refused: managed schema identity mismatch.")
    unexpected_objects = connection.scalar(
        text(
            "SELECT count(*) FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace "
            "WHERE n.nspname !~ '^pg_' AND n.nspname <> 'information_schema' "
            "AND (n.nspname <> 'public' OR pg_get_userbyid(c.relowner) <> 'deploy_buddy' "
            "OR c.relkind IN ('v', 'm', 'f'))"
        )
    )
    if unexpected_objects:
        raise DatabaseSafetyError("Migration refused: unrelated database objects found.")
    foreign_definitions = connection.scalar(
        text(
            "SELECT count(*) FROM pg_namespace WHERE nspname !~ '^pg_' "
            "AND nspname NOT IN ('information_schema', 'public')"
        )
    )
    user_routines = connection.scalar(
        text(
            "SELECT count(*) FROM pg_proc p JOIN pg_namespace n ON n.oid = p.pronamespace "
            "WHERE n.nspname !~ '^pg_' AND n.nspname <> 'information_schema'"
        )
    )
    standalone_types = connection.scalar(
        text(
            "SELECT count(*) FROM pg_type t JOIN pg_namespace n ON n.oid = t.typnamespace "
            "WHERE n.nspname !~ '^pg_' AND n.nspname <> 'information_schema' "
            "AND t.typrelid = 0 AND t.typelem = 0"
        )
    )
    if foreign_definitions or user_routines or standalone_types:
        raise DatabaseSafetyError("Migration refused: unrelated database definitions found.")
