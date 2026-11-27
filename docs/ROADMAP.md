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

### B2.4a — Rename active projects [COMPLETE]
- [x] Allow organization owner/admin to rename an active project via PATCH.
- [x] Preserve project UUID, code and organization; reject unauthorized/archived changes.
- [x] Add a simple "Переименовать" form on active project cards.
- [x] Add integration tests for forbidden access, Origin checks and invalid names.
- [x] Final CI green and merged to main.
- [x] Owner verified rename via VS Code (2026-11-27).

### B2.4b — Archive/restore and change audit [COMPLETE]
- [x] Reversible archive/restore restricted to organization owner/admin.
- [x] Additive event table and database trigger denying audit-row rewrites/deletes.
- [x] Record actor and before/after values atomically for rename/archive/restore.
- [x] Tenant-scoped history API and inline project timeline.
- [x] UI confirmation before status changes; no delete actions.
- [x] Integration tests for permissions, CSRF and audit append-only constraints.
- [x] CI green and changes merged into main (74 Python tests).
- [x] Owner confirmed migration 0003, archive/restore/history locally (2026-11-27).

### B2.4c — Further project settings [LATER]
- Detailed settings (no advertising data yet).
- Production audit hardening: separate DB roles, backups and integrity verification.

## C — Read-only Yandex Direct connector
### C1 — Fixed-contract read client [COMPLETE]
- [x] Verify official API v501 docs, OAuth and developer approval requirements.
- [x] Implement allowlisted Campaigns.get and AgencyClients.get with pagination cap.
- [x] Sanitize upstream errors; keep OAuth token out of persisted configuration.
- [x] Add an interactive terminal-only probe; no token in shell history.
- [x] Offline contract tests using httpx.MockTransport (no real accounts).
- [x] Green GitHub Actions, merged PR and live read-only probe (377 agency clients and 243 campaigns, 2026-11-27).

### C2 — Authorized live-account linkage
#### C2.2a — Non-secret project-account mapping [COMPLETE]
- [x] Implement additive migration 0004 for one Yandex Direct login per project.
- [x] Enforce owner/admin authorization, exact Origin, archived read-only and tenant isolation.
- [x] Record bind/change/unbind in append-only project history.
- [x] Display explicit "configured_unverified" status in the local dashboard.
- [x] Reject client-submitted OAuth token or extra credentials in payload.
- [x] Add deterministic PostgreSQL and HTTP tests (no Yandex calls).
- [x] CI green, PR merged and local migration verified by owner (2026-11-27).

#### C2.2b1 — Local manual OAuth token vault + verified account [IN PROGRESS]
- [x] Build authenticated AES-256-GCM vault, key in separate local Docker volume.
- [x] Add one encrypted agency credential per organization, shared by its projects.
- [x] Import, rotate and remove token from local CLI after MAKO owner/admin password check.
- [x] Add an owner/admin on-demand verification button using AgencyClients.get and Campaigns.get.
- [x] Show campaign count and timestamp of latest success; do not promise continuous connectivity.
- [x] Add offline isolation/security tests and additive migration 0005.
- [ ] CI green and merged; local owner runs key init, token import and project verification.

#### C2.2b2 — Production OAuth authorization/lifecycle [NOT STARTED]
- [x] API-approved OAuth application and local live read-only probe confirmed (2026-11-27).
- [ ] Build OAuth authorization-code flow with CSRF state, exact client ID, and token refresh/expiry handling.
- [ ] Encrypt token with production-grade secret manager and least privilege roles.
- [ ] Implement trusted revocation, rotation, backup/recovery and incident response.
- [ ] Confirm legal/privacy/account authorization requirements before customer deployment.

#### C2.2b3 — Campaign inventory [NOT STARTED]
- [ ] Store selected advertiser's authorized campaign IDs/names with freshness, scoped to MAKO project.
- [ ] Reconcile inventory against actual Yandex Direct UI.

#### C2.2c — Sync and provider status [NOT STARTED]
- [ ] Store safe tenant-bound freshness/status metadata.
- [ ] Add explicit on-demand, bounded read-only sync.
- [ ] No automatic background tasks until token lifecycle and quotas are tested.

### C3 — Statistics ingestion [NOT STARTED]
- [ ] Read Reports TSV, handle 202/429 and quotas, reconcile dates/currency/conversions.
- [ ] Store tenant-scoped statistics with freshness/lineage and sync errors.
- [ ] Build manual refresh, later bounded background sync.


## D — Insight dashboard
- KPI cards, comparisons, campaign reports and data freshness.

## E — AI Analyst + Audit Lite
- Deterministic metric tools, bounded AI explanations and evidence-backed rules.

## F — Controlled client pilot
- Authorized project and privacy/backup/audit/cost gates.
