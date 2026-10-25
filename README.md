# Deploy Buddy

An independent product for public GitHub repositories containing one Node.js web
service, with Render as the planned provider.

**Milestone 2:** validated, explicitly confirmed **dry-run requests only**. Preview
one Node.js web-service proposal, confirm its exact digest, then save the request,
planned operation and audit events atomically in PostgreSQL. The frontend uses
the actual FastAPI endpoints through a fixed loopback proxy. No command executes,
no repository is fetched, and no external integration or resource is created.
Worker execution, Render integration, autonomous repair and AI tribunal are absent.
The reserved recovery columns do not implement recovery behavior.

## Prerequisites

Windows PowerShell, Git, Node.js 20.19 / 22.13 / 24+ (24 tested), Python 3.12+ (3.14 tested),
and Docker Desktop running Linux containers. Commands below start from this
product directory. No reference application files or database are required.

## Install and verify

```powershell
Set-Location D:\DeployBuddy\product
python -m venv backend\.venv
backend\.venv\Scripts\python.exe -m pip install -r backend\requirements-dev.lock
backend\.venv\Scripts\python.exe -m pip install --no-deps -e backend
Set-Location frontend
npm ci --ignore-scripts --no-fund --no-audit
npm run lint
npm run typecheck
npm run build
npx playwright install chromium
Set-Location ..
python scripts\verify_git_safety.py
# After npm run build: checks API, frontend dev and frontend production servers.
python scripts\smoke_local.py
Set-Location backend
.venv\Scripts\python.exe -m ruff check . ..\scripts
.venv\Scripts\python.exe -m ruff format --check . ..\scripts
.venv\Scripts\python.exe -m pytest -q
# Opt-in integration suite: creates and removes its own random local container.
# It ignores the host DATABASE_URL and uses no existing database or named volume.
.venv\Scripts\python.exe -m pytest -q --integration
# Also test the production browser against the actual API + disposable PostgreSQL.
# Requires the frontend build and Chromium above; ports 8000 and 3100 must be free.
.venv\Scripts\python.exe -m pytest -q --integration --browser -s
```

The backend lock records the tested development environment. The frontend lock
pins npm dependencies. Unit-only pytest intentionally skips PostgreSQL tests;
`--integration` must pass before claiming database behavior works.
The linter uses the TypeScript 6 compatibility API while `typecheck` explicitly
uses the retained TypeScript 7.0.2 native compiler. Some Next.js ESLint plugins
still declare ESLint 9 peer ranges: npm reports override warnings with ESLint 10;
the pinned clean install and lint commands have been verified.

## Initialize a new local database

```powershell
Set-Location D:\DeployBuddy\product
python scripts\init_local_env.py
docker compose up -d --wait db
Set-Location backend
.venv\Scripts\python.exe -m alembic upgrade head
```

The initializer creates an ignored product-local `.env` with a generated local
database password and never prints it. It refuses to overwrite an existing file.
The committed `.env.example` files contain placeholders only. No provider token
is needed. Do not use `docker compose config` when sharing output; it resolves
local environment values.

The database binds to `127.0.0.1:55432`, uses a product-specific Compose project
and named volume, and is independent of the reference copy. Stop it with
`docker compose stop db` from the product root; this preserves its local data.

Before any migration DDL, the guard requires a loopback PostgreSQL URL, the
dedicated `deploy_buddy` role, and the exact database name `deploy_buddy_local`
(or `deploy_buddy_test` for tests). It checks the server's actual database, role,
ownership, and absence of user relations, types, routines or additional schemas. A
transaction-level advisory lock serializes initializers, and PostgreSQL DDL runs
inside that transaction. Environment variables override the product `.env`,
but must still pass every guard. No other environment files are discovered.

Migration 0001 remains frozen. Migration 0002 adds a nullable proposal digest
(historical runs are preserved) and the planned-operation table. Upgrades require
the dedicated server identity, a known Alembic revision, the exact known table
and column inventory, product-owned relations, and no unrelated schemas, routines
or standalone types. Repeating `upgrade head` is a safe no-op for a recognized
schema. Empty databases still require the original bootstrap checks. Offline SQL
and destructive downgrades remain disabled. No reset command is provided.

## Start locally

API, in one terminal (no database connection occurs at startup):

```powershell
Set-Location D:\DeployBuddy\product\backend
.venv\Scripts\python.exe -m uvicorn deploy_buddy.main:app --host 127.0.0.1 --port 8000
```

Check `http://127.0.0.1:8000/health`; API documentation is at `/docs`.
Health reports process liveness, not database readiness.

Frontend, in another terminal:

```powershell
Set-Location D:\DeployBuddy\product\frontend
npm run dev
```

Open `http://127.0.0.1:3000`. For a production smoke test, use `npm run build`
then `npm start` instead. Stop either process with Ctrl+C.

## Demonstrate a dry-run request locally

Initialize and migrate the local database with the commands above, then start
the API on port 8000 and the frontend on port 3000. No provider credentials are needed.

1. Open `http://127.0.0.1:3000`. Enter `https://github.com/example/service` and
   service name `demo-service`. The example URL is only a syntax fixture.
2. Click **Preview dry-run**. Review the canonical repository, service name,
   one Node.js web service, Render proposal, and build/start commands.
3. Check the explicit confirmation box and click **Save confirmed dry-run**.
4. Observe status **planned**, the request UUID, confirmation timestamp, saved
   operation, and `new → queued → planned` audit trail.
5. Check and save the same proposal again: it returns the same request and events.
   Refresh the page and use **Load last saved request**, or paste its UUID and
   click **Load request status**. Editing settings removes the old preview and
   requires another confirmation. Use a non-GitHub URL to see backend rejection.

The request stays `planned` indefinitely in this milestone. No background work runs.

## API contract and validation

| Endpoint | Behavior |
| --- | --- |
| `POST /requests/preview` | Validates settings and returns a deterministic proposal and SHA-256 digest. No database access. |
| `POST /requests` | Requires `confirmed: true`, the preview digest and a UUID `idempotency_key`; commits all records together. |
| `GET /requests/{uuid}` | Returns saved status, confirmation time, operation and ordered audit events; unknown IDs return 404. |
| `GET /health` | Process liveness; no database/provider access. |

Settings are `repository_url`, `service_name`, `build_command`, `start_command`,
`runtime`, `service_type`, `provider`, and `mode`. Only HTTPS URLs of the form
`https://github.com/owner/repository` are allowed; optional `.git` and trailing
slash normalize away, and owner/repository names normalize to lowercase.
Credentials, other hosts, SSH, ports, URL escapes, query strings, fragments and
subpaths are rejected. **This is URL syntax validation, not proof that a repository
exists, is public, or contains a Node.js web service.** No GitHub access occurs.

Exactly one `node` / `web` service with planned provider `render` and mode
`dry_run` is supported. Names must be 1–63 lowercase letters, digits or hyphens,
start with a letter and end with a letter/digit. Allowed build commands are
`npm ci` or `npm ci && npm run build`; start command is `npm start`. Defaults
apply when those settings are omitted. Extra fields (including environment
variables, tokens, region, pricing tier and multiple services) are rejected.
The proposal does not imply provider pricing, availability or executable API payloads.

Confirmation is a strict JSON boolean, tied to all displayed operations and
the dry-run notice. Changed settings or a stale digest return 409. Same UUID and
proposal return the original result (200); the first submission returns 201.
Reusing a UUID for another proposal returns 409. PostgreSQL's unique constraint
arbitrates concurrent retries. A failed transaction saves nothing, and the same
key can safely be retried. Preserve the key after a network error.

Validation responses never echo submitted values. Database errors return a
generic 503 without connection details, and SQL parameters are hidden. Responses
use explicit schemas and omit credentials, internal provider references and the
idempotency key. No application code logs request bodies or loads provider tokens.
The external-integration boundary rejects every mode before invoking a client or
callback, and the request service has no provider execution path. These are local
development endpoints; authentication and multi-user access are outside this milestone.

## Structure and boundaries

- `frontend/`: Next.js App Router preview, confirmation and saved-status interface.
- `backend/src/deploy_buddy/api/`: HTTP boundary.
- `backend/src/deploy_buddy/services/`: deterministic planner and transactional request service.
- `backend/src/deploy_buddy/db/`: SQLAlchemy runs, events, logs and migration guard.
- `backend/src/deploy_buddy/providers/`: fail-closed integration boundary; no Render adapter.
- `backend/src/deploy_buddy/worker/`: reserved separate Python worker package.
- `backend/migrations/`: frozen schema revisions with guarded local upgrades.
- `backend/tests/`: validation, confirmation, secret handling, integration denial,
  concurrent idempotency, rollback, migrations and optional production browser tests.
- `scripts/`: local environment initialization and Git ignore verification.

Git is initialized only here. There is no remote and nothing is published.
Review `git status --short`, `git ls-files --others --exclude-standard`, and
`git diff --cached --name-only` before any first commit. Inspect file contents
as well: ignore rules cannot detect secrets pasted into ordinary source files.
Never force-add environment files, credentials, generated secrets or local data.

## Milestone boundary

Milestone 2 stops at persisted dry-run plans. Worker claiming/recovery, Render
calls, repository inspection, autonomous repair and AI tribunal are later work.
No GitHub push, external deployment, provider change or publication is performed.
See `MILESTONE-2.md` for changed files and exact verification results.

Documentation references: [Next.js installation](https://nextjs.org/docs/app/getting-started/installation),
[FastAPI first steps](https://fastapi.tiangolo.com/tutorial/first-steps/),
[SQLAlchemy declarative tables](https://docs.sqlalchemy.org/en/20/orm/declarative_tables.html),
[Alembic runtime](https://alembic.sqlalchemy.org/en/latest/api/runtime.html),
[PostgreSQL official image](https://hub.docker.com/_/postgres), and
[Starlette test client](https://www.starlette.io/testclient/).
