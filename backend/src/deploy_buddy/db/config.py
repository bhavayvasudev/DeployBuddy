import os
from pathlib import Path

from dotenv import load_dotenv
from sqlalchemy.engine import URL, make_url
from sqlalchemy.exc import ArgumentError

PRODUCT_ROOT = Path(__file__).resolve().parents[4]
ALLOWED_DATABASES = frozenset({"deploy_buddy_local", "deploy_buddy_test"})


class DatabaseSafetyError(RuntimeError):
    """A safe, credential-free explanation for refusing database operations."""


def validate_database_url(raw: str) -> URL:
    try:
        url = make_url(raw)
    except (ArgumentError, ValueError):
        raise DatabaseSafetyError("DATABASE_URL is invalid; connection details withheld.") from None
    if url.drivername != "postgresql+psycopg":
        raise DatabaseSafetyError("Only PostgreSQL via psycopg is supported.")
    if url.database not in ALLOWED_DATABASES:
        raise DatabaseSafetyError(
            "Refusing database: name must be deploy_buddy_local or deploy_buddy_test."
        )
    if url.host not in {"127.0.0.1", "localhost", "::1"} or url.query:
        raise DatabaseSafetyError(
            "Only explicit loopback connections without URL options are allowed."
        )
    if url.username != "deploy_buddy" or not url.password or url.port is None:
        raise DatabaseSafetyError(
            "Use the dedicated deploy_buddy role, password and explicit port."
        )
    return url


def database_url() -> URL:
    # Never discover environment files outside this independent product.
    load_dotenv(PRODUCT_ROOT / ".env", override=False)
    raw = os.environ.get("DATABASE_URL", "")
    return validate_database_url(raw)
