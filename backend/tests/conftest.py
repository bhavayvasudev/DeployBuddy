import os
import secrets
import subprocess
import time
import uuid

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.engine import URL
from sqlalchemy.exc import OperationalError


def pytest_addoption(parser):
    parser.addoption(
        "--integration", action="store_true", help="Run disposable Docker database tests"
    )
    parser.addoption("--browser", action="store_true", help="Run production frontend browser tests")


def pytest_collection_modifyitems(config, items):
    for item in items:
        if "browser" in item.keywords and not config.getoption("--browser"):
            item.add_marker(
                pytest.mark.skip(reason="Use --integration --browser after frontend build")
            )
    if not config.getoption("--integration"):
        for item in items:
            if "integration" in item.keywords:
                item.add_marker(
                    pytest.mark.skip(reason="Use --integration to create a disposable DB")
                )


@pytest.fixture(scope="session")
def postgres_url():
    """Create only our own random container; never consume DATABASE_URL from the host."""
    name = f"deploy-buddy-test-{uuid.uuid4().hex}"
    password = secrets.token_urlsafe(32)
    child_env = {**os.environ, "POSTGRES_PASSWORD": password}
    try:
        subprocess.run(
            [
                "docker",
                "run",
                "--detach",
                "--rm",
                "--name",
                name,
                "--label",
                "product=deploy-buddy-test",
                "--env",
                "POSTGRES_PASSWORD",
                "--env",
                "POSTGRES_USER=deploy_buddy",
                "--env",
                "POSTGRES_DB=deploy_buddy_test",
                "--publish",
                "127.0.0.1::5432",
                "postgres:17",
            ],
            env=child_env,
            check=True,
            capture_output=True,
            text=True,
            timeout=180,
        )
        port_info = subprocess.run(
            ["docker", "port", name, "5432/tcp"],
            check=True,
            capture_output=True,
            text=True,
            timeout=10,
        ).stdout.strip()
        url = URL.create(
            "postgresql+psycopg",
            username="deploy_buddy",
            password=password,
            host="127.0.0.1",
            port=int(port_info.rsplit(":", 1)[1]),
            database="deploy_buddy_test",
        )
        engine = create_engine(url, hide_parameters=True, connect_args={"connect_timeout": 2})
        try:
            deadline = time.monotonic() + 45
            while True:
                try:
                    with engine.connect() as connection:
                        connection.execute(text("SELECT 1"))
                    break
                except OperationalError:
                    if time.monotonic() >= deadline:
                        pytest.fail("Disposable PostgreSQL did not become ready.")
                    time.sleep(0.5)
            yield url
        finally:
            engine.dispose()
    finally:
        # Exact generated container name; no volumes or existing containers are touched.
        subprocess.run(
            ["docker", "rm", "--force", "--volumes", name], capture_output=True, timeout=15
        )


@pytest.fixture
def empty_database(postgres_url):
    engine = create_engine(postgres_url, hide_parameters=True)
    # Cleanup is restricted to the random disposable container created above.
    with engine.begin() as connection:
        connection.execute(text("DROP SCHEMA public CASCADE"))
        connection.execute(text("CREATE SCHEMA public AUTHORIZATION deploy_buddy"))
    try:
        yield engine
    finally:
        with engine.begin() as connection:
            connection.execute(text("DROP SCHEMA public CASCADE"))
            connection.execute(text("CREATE SCHEMA public AUTHORIZATION deploy_buddy"))
        engine.dispose()
