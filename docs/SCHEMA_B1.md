# Milestone B1 — tenant database schema

**Scope:** organizations, users, projects, memberships, migrations and tests. No authentication or tenant-protected HTTP endpoints yet.

## Tables

| Table | Purpose | Key and policy |
| --- | --- | --- |
| `organizations` | Agency / customer org | UUID id; global unique slug |
| `users` | Identity record; login not yet enabled | UUID id; case-insensitive unique email |
| `organization_memberships` | Membership within org | (organization_id, user_id) PK; owner/admin/member |
| `projects` | Marketing project under org | UUID id; unique (organization_id, slug); active/archived |
| `project_memberships` | Explicit membership in project | (project_id, user_id) PK; manager/editor/viewer |

**Cross-tenant protection at database level:** two composite foreign keys on project_memberships ensure a project and the user membership are part of the same organization. This is only referential integrity; **runtime authorization is not implemented**.

Organization ownership does not automatically imply project access in B1. We will settle owner/admin inheritance rules before enabling endpoints in B2.

## Run the migration using VS Code's PowerShell terminal

After `git pull`, keep PostgreSQL data and rebuild the backend container:

```powershell
docker compose up --build -d
docker compose exec backend alembic -c /app/alembic.ini upgrade head
docker compose exec backend alembic -c /app/alembic.ini current
```

The last line should show `0001_initial_tenants (head)`.

To display the created tables:

```powershell
docker compose exec db sh -c 'psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" -c "\dt"'
```

Do not run `docker compose down -v`: that deletes PostgreSQL volumes.

## CI and cost

The free standard Ubuntu Actions runner starts an **ephemeral PostgreSQL 17 container**. CI applies migrations, detects model/schema drift, runs unit tests and verifies cross-tenant FK and unique-email behavior. Real advertising or customer data is never used.

Database integration tests run only with explicit `MAKO_TEST_DATABASE_URL`, which **must refer to a disposable database**. Never run them against an actual project database.

## What is deferred until B2

- Authentication, sessions, invites and access policy.
- Tenant-bound API read/write operations and forbidden-access tests.
- Audit trail and safely provisioned initial owner.
- Password/OAuth storage and secrets (none present in B1).

Do not expose the backend to external networks until these are implemented and security-reviewed.
