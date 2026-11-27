# Milestones

## A — Local scaffold [COMPLETE]
- [x] Monorepo skeleton: backend, frontend, docs, GitHub.
- [x] FastAPI liveness and database readiness endpoints.
- [x] Next.js local page that checks backend availability.
- [x] PostgreSQL with persistent Docker volume.
- [x] Successful local Docker Compose launch (owner confirmed 2026-11-27).
- [x] Read-only GitHub Actions: backend and frontend checks.
- [x] Portable npm lockfile and reproducible npm ci.

## B — Roles and projects
### B1 — Database foundation [COMPLETE]
- [x] Initial ORM model and Alembic migration for organizations, users and projects.
- [x] Composite foreign keys protecting cross-organization memberships.
- [x] 13 tests and schema drift check in GitHub Actions.
- [x] Local migration applied (owner confirmed 2026-11-27).

### B2.1 — Access policy and tenant-scoped queries [COMPLETE]
- [x] Define owner/admin/member and manager/editor/viewer project permissions.
- [x] Tenant-scoped project query implementation.
- [x] Pure and PostgreSQL integration tests for permitted and forbidden access.
- [x] Green CI for the pull request (35 tests passed, no failed checks).
- [x] Merge to main and verify final CI.

### B2.2 — Local login and first project view [COMPLETE]
- [x] Design DB-backed sessions and one-time owner bootstrap.
- [x] Implement local-only login and logout (no hardcoded credentials).
- [x] Implement protected read-only project endpoints and frontend list.
- [x] 47 backend tests green in PR CI; frontend build green.
- [x] Merge to main and verify final CI.
- [x] Local bootstrap, login and demonstration project verified by owner (2026-11-27).
- [x] Test unauthorized, cross-organization, archived and missing-project access.

### B2.3 — Create real empty projects [COMPLETE]
- [x] Add POST project API restricted to verified organization owners/admins with Origin check.
- [x] Validate normalized project name and per-organization unique slug; return 409 for duplicates.
- [x] Add a project creation form in the local dashboard.
- [x] Add integration tests for unauthorized members, outsiders, CSRF, validation and duplicate codes.
- [x] Final CI green and merged to main (56 tests, frontend build).
- [x] Owner confirmed local creation and display of a new project (2026-11-27).

### B2.4a — Rename active projects [IN PROGRESS]
- [x] Allow organization owner/admin to rename an active project via PATCH.
- [x] Preserve project UUID, code and organization; reject unauthorized/archived changes.
- [x] Add a simple "Переименовать" form on active project cards.
- [x] Add integration tests for forbidden access, Origin checks and invalid names.
- [ ] Final CI green and merged to main.
- [ ] Owner verifies rename via VS Code.

### B2.4b — Archive/restore and audit history [LATER]
- Non-destructive archive and restore with safe confirmations.
- Immutable history of project metadata changes and actor identity.
- Project settings beyond display name (no advertising data yet).

## C — Read-only Yandex connector
- Confirm API requirements and permissions.
- Implement authorized read-only ingestion and sync status.
- Reconcile reports against source data.

## D — Insight dashboard
- KPI cards, comparisons, campaign reports and data freshness.

## E — AI Analyst + Audit Lite
- Deterministic metric tools, bounded AI explanations and evidence-backed rules.

## F — Controlled client pilot
- Authorized project and privacy/backup/audit/cost gates.
