"""Start the API and Next.js on loopback, check responses, stop our process trees."""

import json
import os
import socket
import subprocess
import time
from pathlib import Path
from tempfile import TemporaryDirectory
from urllib.error import URLError
from urllib.request import ProxyHandler, Request, build_opener

ROOT = Path(__file__).resolve().parents[1]
OPENER = build_opener(ProxyHandler({}))


def check_server(command: list[str], cwd: Path, port: int, path: str, expected: str) -> None:
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", port))  # Refuse to test an already-running server.
    local = ROOT / ".local"
    local.mkdir(exist_ok=True)
    with TemporaryDirectory(prefix="smoke-", dir=local) as directory:
        with (Path(directory) / "server.log").open("w", encoding="utf-8") as output:
            child_env = {**os.environ, "NEXT_TELEMETRY_DISABLED": "1"}
            process = subprocess.Popen(
                command, cwd=cwd, env=child_env, stdout=output, stderr=subprocess.STDOUT
            )
            try:
                deadline = time.monotonic() + 30
                while True:
                    if process.poll() is not None:
                        raise RuntimeError("Smoke server exited before readiness; inspect startup.")
                    try:
                        with OPENER.open(f"http://127.0.0.1:{port}{path}", timeout=2) as response:
                            assert response.status == 200
                            assert expected in response.read().decode("utf-8")
                        break
                    except (URLError, TimeoutError):
                        if time.monotonic() >= deadline:
                            raise RuntimeError("Local server readiness timed out.") from None
                        time.sleep(0.2)
                if port == 8000:
                    request = Request("http://127.0.0.1:8000/openapi.json")
                    with OPENER.open(request, timeout=2) as response:
                        assert set(json.load(response)["paths"]) == {
                            "/health",
                            "/requests/preview",
                            "/requests",
                            "/requests/{request_id}",
                        }
                print(f"PASS: HTTP 200 from 127.0.0.1:{port}{path}; expected content present.")
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


def main() -> None:
    executable = ROOT / "backend" / ".venv" / "Scripts" / "python.exe"
    check_server(
        [
            str(executable),
            "-m",
            "uvicorn",
            "deploy_buddy.main:app",
            "--host",
            "127.0.0.1",
            "--port",
            "8000",
        ],
        ROOT / "backend",
        8000,
        "/health",
        "deploy-buddy",
    )
    for mode in ("dev", "start"):
        # Run the same Next CLI arguments as the documented npm commands.
        check_server(
            ["node", "node_modules/next/dist/bin/next", mode, "--hostname", "127.0.0.1"],
            ROOT / "frontend",
            3000,
            "/",
            "Preview dry-run",
        )


if __name__ == "__main__":
    main()
