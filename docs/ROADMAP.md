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
### B1 — Database foundation [IN PROGRESS]
- [x] Initial ORM model and Alembic migration: organizations, users, organization memberships, projects, project memberships.
- [x] Referential integrity across organization and project memberships.
- [x] Integration tests using disposable PostgreSQL in GitHub Actions.
- [x] CI is green after PR (13 tests, schema migration and Alembic drift check).
- [ ] Apply first migration to owner's local Docker environment.

### B2 — Authentication and access [NOT STARTED]
- [ ] Design and test secure authentication/session approach.
- [ ] Project-level authorization and negative access tests.
- [ ] First safe owner/organization/project setup.
- [ ] API endpoints only after access controls exist.

## C — Read-only Yandex connector
- Verify API policies and permissions.
- Authorized read-only connector, ingestion and sync status.
- Metric reconciliation against Direct source.

## D — Insight dashboard
- Real KPI cards, period comparisons, project reports and data freshness.

## E — AI Analyst + Audit Lite
- Deterministic metric functions, limited AI explanations, evidence-linked findings.

## F — Controlled client pilot
- One authorized project with data protection, backups, auditability, and spending caps.
