from alembic import context
from sqlalchemy import create_engine, text

from deploy_buddy.db.config import DatabaseSafetyError, database_url
from deploy_buddy.db.models import Base
from deploy_buddy.db.safety import assert_migration_target

if context.is_offline_mode():
    raise DatabaseSafetyError("Offline migrations cannot verify database safety and are disabled.")
engine = create_engine(database_url(), hide_parameters=True, connect_args={"connect_timeout": 5})
try:
    with engine.connect() as connection, connection.begin():
        connection.execute(text("SET LOCAL lock_timeout = '5s'"))
        connection.execute(text("SET LOCAL statement_timeout = '30s'"))
        connection.execute(text("SET LOCAL search_path = public"))
        # Serialize Deploy Buddy initializers. Lock and checks precede all DDL.
        connection.execute(text("SELECT pg_advisory_xact_lock(548672901)"))
        assert_migration_target(connection)
        context.configure(connection=connection, target_metadata=Base.metadata)
        with context.begin_transaction():
            context.run_migrations()
finally:
    engine.dispose()
