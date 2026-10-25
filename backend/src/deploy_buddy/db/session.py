from contextlib import contextmanager
from functools import lru_cache

from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from deploy_buddy.db.config import database_url


@lru_cache(maxsize=1)
def application_engine():
    # Lazy: liveness and preview work without a database. Never log SQL parameters.
    return create_engine(
        database_url(),
        hide_parameters=True,
        echo=False,
        connect_args={"connect_timeout": 5, "options": "-c statement_timeout=10000"},
    )


@contextmanager
def application_session():
    with Session(application_engine()) as session:
        yield session


def request_session():
    # Return a factory so HTTP body validation precedes any database configuration/access.
    return application_session
