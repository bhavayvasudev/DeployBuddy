"""Verify repository boundaries and ignores without creating secret-like files."""

import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
IGNORED = [
    ".env",
    ".env.local",
    ".env.backup",
    "backend/.env",
    "frontend/.env.production.local",
    "backend/settings.env",
    "backend/settings.env.backup",
    "private.key",
    "identity.pem",
    "key.p12",
    "key.pfx",
    "id_rsa",
    "id_ed25519",
    "credentials.local.json",
    "secrets.json",
    "service-account.local.json",
    ".npmrc",
    ".pypirc",
    ".netrc",
    ".gitconfig",
    "frontend/node_modules/probe",
    "frontend/.next/probe",
    "frontend/out/probe",
    "backend/.venv/probe",
    "backend/venv/probe",
    "backend/__pycache__/probe.pyc",
    "backend/.pytest_cache/probe",
    ".local/probe",
    "data/probe",
    "pgdata/probe",
    "local.db",
    "local.db-wal",
    "local.sqlite3",
    "backup.dump",
    "backup.sql",
    "debug.log",
    "logs/probe",
    "dist/probe",
    "build/probe",
    "frontend/test.tsbuildinfo",
    ".coverage",
]
TEMPLATES = [".env.example", "frontend/.env.example"]


def git(*args: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["git", "-C", str(ROOT), *args], capture_output=True, text=True, check=False
    )


def main() -> None:
    top = git("rev-parse", "--show-toplevel")
    if top.returncode or Path(top.stdout.strip()).resolve() != ROOT:
        raise SystemExit("Repository root is not product/.")
    result = git("check-ignore", "--no-index", "--", *IGNORED, *TEMPLATES)
    actual = set(result.stdout.splitlines())
    if actual != set(IGNORED):
        raise SystemExit(f"Ignore verification failed: {sorted(actual ^ set(IGNORED))}")
    if git("remote").stdout.strip():
        raise SystemExit("Unexpected Git remote: review before continuing.")
    staged = git("diff", "--cached", "--name-only", "--diff-filter=ACMR").stdout.splitlines()
    if staged:
        blocked = git("check-ignore", "--no-index", "--", *staged).stdout.splitlines()
        if blocked:
            raise SystemExit(f"Ignored files found in the index: {blocked}")
    print(
        f"PASS: product-local repository; {len(IGNORED)} ignored probes; "
        f"{len(TEMPLATES)} shareable templates; {len(staged)} staged files; no remote."
    )


if __name__ == "__main__":
    main()
