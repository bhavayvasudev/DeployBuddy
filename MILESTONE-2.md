# Milestone 2: explicitly confirmed local dry-run requests

Completed locally on 2026-10-25. Scope ends at a persisted plan. No worker,
Render adapter, autonomous repair or AI tribunal was implemented. No GitHub
push, external deployment, paid resource, provider setting change or publication
occurred. The reference application was not modified.

## Behavior

- `POST /requests/preview` validates the closed single Node.js web-service
  configuration and canonical GitHub HTTPS URL syntax. It returns the complete
  proposal, dry-run notice and deterministic SHA-256 digest without database access.
- `POST /requests` requires a strict `confirmed: true`, that proposal's digest,
  and a UUID idempotency key. Settings changed after review require a fresh preview.
- One PostgreSQL transaction saves the confirmed request in `planned` status,
  one planned operation and two ordered status events (`new → queued → planned`).
  Success is returned only after commit. A failed operation/event write rolls
  everything back; the original submission key can be retried.
- Duplicate submissions return the original request without extra operations or
  events. PostgreSQL arbitrates concurrent duplicates. Reusing the key for a
  different proposal returns 409. First submission returns 201; duplicates 200.
- `GET /requests/{uuid}` exposes the saved status, operation, timestamps and audit
  trail. The UI uses the actual API through a fixed loopback Next.js rewrite.
- The UI displays the exact proposal before showing an unchecked confirmation
  box. Editing settings removes that proposal and confirmation. Retry preserves
  the submission key. A saved ID can be loaded again, including after page reload.
- The planner and persistence service have no HTTP client, subprocess, shell or
  provider path. No commands execute and no repository is fetched. A separate
  fail-closed external-integration boundary raises before invoking any callback
  in dry-run mode; live and unknown modes are also unavailable.
- Extra fields, provider tokens and environment variables are rejected. Commands
  are restricted to the documented npm choices. Validation errors omit submitted
  values; database errors return a generic 503. SQL parameters are hidden, API
  outputs are explicit schemas, and no application code logs request bodies or
  loads provider credentials.

## Schema and migration safety

The frozen Milestone 1 revision was preserved. Revision 0002 adds the saved
proposal digest and `deployment_operations`, constrained to a single sequence
and supported planned operation. Historical rows are preserved with null digests
and are not exposed as confirmed Milestone 2 requests.

The migration guard now accepts an empty dedicated local database or a recognized
Milestone 1/2 schema. It checks database/role ownership, known revision, exact table
and column inventory, owned relations, and absence of unrelated schemas, routines
or standalone types. Migrations set `search_path` explicitly, take the existing
advisory lock and use transactional DDL. Repeated upgrades are safe no-ops for a
recognized schema. Offline migration and destructive downgrade remain disabled.

## Exact final verification results

Commands below were executed with Python 3.14.0, Node 24.12.0, PostgreSQL 17 in
disposable containers, Next.js 16.4.3, native TypeScript 7.0.2 and ESLint 10.13.0.

| Command | Final result |
| --- | --- |
| Backend: `.venv\Scripts\python.exe -m pytest -q --integration --browser --tb=short -s` | **95 passed in 13.25s**, no skipped tests. Includes the production browser harness, whose **3 browser scenarios passed in 3.5s**. |
| Backend: `.venv\Scripts\python.exe -m ruff check . ..\scripts` | Passed: `All checks passed!` |
| Backend: `.venv\Scripts\python.exe -m ruff format --check . ..\scripts` | Passed: `30 files already formatted` |
| Backend: `.venv\Scripts\python.exe -m pip check` | Passed: `No broken requirements found.` |
| Frontend: `npm ci --ignore-scripts --no-fund --no-audit` | Passed; 346 packages installed. ESLint peer-range warnings described below. |
| Frontend: `npm run lint` | Passed with `--max-warnings=0`. |
| Frontend: `npm run typecheck` | Passed using the explicitly selected native TypeScript 7 compiler. |
| Frontend: `npm run build` | Passed; `/` and `/_not-found` generated successfully. |
| Frontend: `npm audit --omit=dev --audit-level=high` | Passed: `found 0 vulnerabilities`. |
| Product: `python scripts\smoke_local.py` | Passed: HTTP 200 and expected content from API, frontend development server and frontend production server; OpenAPI paths verified. |
| Product: `python scripts\verify_git_safety.py` | Passed: 41 ignored-path probes, 2 shareable templates, 0 staged files and no remote. |
| Disposable container cleanup check | No containers with label `product=deploy-buddy-test` remained. |

Coverage includes invalid hosts/protocols/credentials/ports/escapes/subpaths,
invalid names/runtimes/commands/settings, strict/missing confirmation, stale
proposals, unknown IDs, duplicate/conflicting/concurrent submissions, request
transaction rollback, schema-upgrade rollback, Milestone 1 data preservation,
unrelated-schema refusal, malformed JSON and secret-safe errors. Tests poison
outbound Python sockets throughout preview/submission/status, supply unused
provider-token sentinels, and verify external callbacks are never invoked.
Browser scenarios cover actual API persistence/reload/idempotent retry, editing
after review, and backend rejection of an unsupported host.

Initial checks found formatting/import issues, an unsupported TypeScript API
for the linter, an ambiguous browser alert selector, and incomplete Windows
process-tree cleanup in the test harness. These were corrected before the final
successful runs. One intermediate browser run also overlapped dependency
reinstallation and was rerun after installation completed.

## Remaining limitations and tooling notes

- **Offline URL syntax validation cannot verify repository existence, public
  visibility or Node.js contents.** This is stated in the preview, UI and README.
  No remote inspection is implied by a `planned` status.
- Commands are intentionally limited to `npm ci` or `npm ci && npm run build`,
  with `npm start`. There are no arbitrary shell commands, environment variables,
  multiple services, provider pricing choices or executable Render API payloads.
- Requests remain `planned`; there is no worker, provider execution, authentication,
  multi-user authorization or recovery mechanism in this local milestone.
- Some dependencies in Next.js's ESLint configuration still declare ESLint 9
  peer ranges, so clean npm installation emits peer override warnings with ESLint
  10. The clean install and strict lint check both pass. The linter uses the
  TypeScript 6 compatibility API while the explicit typecheck command retains
  TypeScript 7.0.2, following [Microsoft's side-by-side guidance](https://devblogs.microsoft.com/typescript/announcing-typescript-7-0/#running-side-by-side-with-typescript-6-0).
- No known failing checks remain. Only disposable test databases were migrated;
  the persistent Compose database was not started or changed during this milestone.

## Demonstrate locally

From `D:\DeployBuddy\product`, initialize the ignored local environment only if
it does not already exist, start PostgreSQL, and apply the guarded migration:

```powershell
if (!(Test-Path .env)) { python scripts\init_local_env.py }
docker compose up -d --wait db
Set-Location backend
.venv\Scripts\python.exe -m alembic upgrade head
.venv\Scripts\python.exe -m uvicorn deploy_buddy.main:app --host 127.0.0.1 --port 8000
```

In another terminal:

```powershell
Set-Location D:\DeployBuddy\product\frontend
npm run dev
```

Open `http://127.0.0.1:3000`. Use `https://github.com/example/service` and name
`demo-service` as a syntax-only fixture. Preview the proposal, inspect its single
operation, check the explicit confirmation box, and save. Observe `planned`, the
request UUID, the operation and both audit events. Confirm/save the same proposal
again to observe the same UUID with no new events. Refresh and click **Load last
saved request**, or paste the UUID and load its status. Change a setting to see
confirmation reset; try another host to see backend validation reject it.

For production browser verification, stop local servers on ports 8000/3100,
run `npm run build` and `npx playwright install chromium` in `frontend`, then
run the full backend pytest command above. The harness creates its own disposable
database and starts/stops its own local API and production frontend. It never
uses the persistent Compose database. No provider credentials are needed.

## Changed-file inventory

All paths are relative to `product/`. The product had no commits at the start,
so Git reports the entire product as untracked; the list below distinguishes
this milestone's edits from its existing foundation. Nothing was staged or committed.

New files:

- `MILESTONE-2.md`
- `backend/migrations/versions/0002_dry_run_requests.py`
- `backend/src/deploy_buddy/api/requests.py`
- `backend/src/deploy_buddy/api/schemas.py`
- `backend/src/deploy_buddy/db/session.py`
- `backend/src/deploy_buddy/providers/boundary.py`
- `backend/src/deploy_buddy/services/planning.py`
- `backend/src/deploy_buddy/services/requests.py`
- `backend/tests/test_browser_integration.py`
- `backend/tests/test_requests.py`
- `backend/tests/test_requests_integration.py`
- `frontend/eslint.config.mjs`
- `frontend/next.config.ts`
- `frontend/playwright.config.ts`
- `frontend/tests/dry-run.spec.ts`

Updated files:

- `README.md`
- `backend/migrations/env.py`
- `backend/pyproject.toml`
- `backend/src/deploy_buddy/db/models.py`
- `backend/src/deploy_buddy/db/safety.py`
- `backend/src/deploy_buddy/main.py`
- `backend/tests/conftest.py`
- `backend/tests/test_database_integration.py`
- `frontend/.env.example`
- `frontend/app/globals.css`
- `frontend/app/layout.tsx`
- `frontend/app/page.tsx`
- `frontend/package.json`
- `frontend/package-lock.json`
- `scripts/smoke_local.py`
