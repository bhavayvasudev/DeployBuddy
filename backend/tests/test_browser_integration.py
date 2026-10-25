"""Opt-in production browser flow, using only our disposable PostgreSQL container."""

import os
import socket
import subprocess
import time
from pathlib import Path
from tempfile import TemporaryDirectory
from urllib.error import URLError
from urllib.request import ProxyHandler, build_opener

import pytest
from test_database_integration import migrate


@pytest.mark.integration
@pytest.mark.browser
def test_production_browser_flow(monkeypatch, empty_database):
    root = Path(__file__).resolve().parents[2]
    for port in (8000, 3100):
        with socket.socket() as probe:
            probe.bind(("127.0.0.1", port))  # Refuse to use unrelated local servers.
    migrate(monkeypatch, empty_database)
    local = root / ".local"
    local.mkdir(exist_ok=True)
    with TemporaryDirectory(prefix="browser-", dir=local) as directory:
        with (Path(directory) / "api.log").open("w", encoding="utf-8") as output:
            process = subprocess.Popen(
                [
                    str(root / "backend/.venv/Scripts/python.exe"),
                    "-m",
                    "uvicorn",
                    "deploy_buddy.main:app",
                    "--host",
                    "127.0.0.1",
                    "--port",
                    "8000",
                    "--no-access-log",
                ],
                cwd=root / "backend",
                env={
                    **os.environ,
                    "DATABASE_URL": empty_database.url.render_as_string(hide_password=False),
                },
                stdout=output,
                stderr=subprocess.STDOUT,
            )
            try:
                opener = build_opener(ProxyHandler({}))
                deadline = time.monotonic() + 20
                while True:
                    if process.poll() is not None:
                        pytest.fail("Browser API exited before readiness.")
                    try:
                        with opener.open("http://127.0.0.1:8000/health", timeout=2) as response:
                            assert response.status == 200
                        break
                    except (URLError, TimeoutError):
                        if time.monotonic() > deadline:
                            pytest.fail("Browser API readiness timed out.")
                        time.sleep(0.1)
                result = subprocess.run(
                    ["node", "node_modules/@playwright/test/cli.js", "test"],
                    cwd=root / "frontend",
                    env={**os.environ, "NEXT_TELEMETRY_DISABLED": "1"},
                    text=True,
                    capture_output=True,
                    timeout=120,
                )
                assert result.returncode == 0, result.stdout + result.stderr
                print(result.stdout)
            finally:
                if os.name == "nt":
                    subprocess.run(
                        ["taskkill", "/PID", str(process.pid), "/T", "/F"],
                        capture_output=True,
                        timeout=10,
                    )
                else:
                    process.terminate()
                process.wait(timeout=10)
