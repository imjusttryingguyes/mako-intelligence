# B2.4b — Reversible archive/restore and project change history

Local development only. This change preserves existing organizations, users,
projects and memberships. It adds `project_events` in migration
`0003_project_events`. It does **not** destroy or rewrite existing project data.

## User-visible behavior
- Organization owners/admins can archive active projects, or restore archived projects.
- Archiving **does not delete** the project, data or user memberships.
- Archived projects remain visible but read-only per B2.1 permission rules.
- Every state change requires an explicit confirmation in the UI.
- Only organization owners/admins may see project metadata history.
- The latest 100 history events include actor display name and action timestamp.
- Historical changes from before this migration are **not available**.
- A no-op rename (same normalized name) does not generate an event.
- There are no destructive delete operations.

## Security and audit behavior
- Authenticated identity must come from the server-side session; never user input.
- Mutations require the exact configured frontend Origin.
- Missing or cross-org project IDs yield 404. Unauthorized normal members receive 403.
- A double archive or double restore yields 409 without an event.
- The server locks the project row during status transitions, avoiding concurrent
  duplicate state changes on PostgreSQL.
- Project changes and corresponding audit rows commit in the same DB transaction.
- A PostgreSQL trigger rejects UPDATE/DELETE of existing audit rows. A privileged
  DB owner can still disable/drop the trigger, so **this is not production-grade,
  tamper-proof audit logging**.
- No production HTTPS, backup/restore, separate DB least-privilege roles,
  rate limits or independent audit integrity checks yet.

## Local VS Code commands
```powershell
git pull
docker compose up --build -d
docker compose exec backend alembic -c /app/alembic.ini upgrade head
docker compose exec backend alembic -c /app/alembic.ini current
```

Expect `0003_project_events (head)`.

Open `http://localhost:3000`. Rename a test project, view **История**,
archive it with confirmation and restore it. Confirm the timeline contains all
three events and that the project code/UUID remain unchanged.

**Never use `docker compose down -v`**: it destroys the local DB volume.
**Do not downgrade migration 0003 after writing audit events**: downgrading
drops the event table and loses change history.

## Test environment
GitHub Actions applies `upgrade head` to an **ephemeral** PostgreSQL 17
database and verifies model/schema drift and access policy. Synthetic test
records use rollback; no client data or paid services are involved.
