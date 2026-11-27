# Milestones

## A — Local scaffold
- [x] Monorepo skeleton: backend, frontend, docs, GitHub.
- [x] Read-only FastAPI liveness and DB readiness endpoints.
- [x] Next.js local page that checks backend availability.
- [x] PostgreSQL container in Compose with persistent volume.
- [x] Backend unit tests and lint rules.
- [x] Verify GitHub Actions backend and frontend jobs.
- [x] Run full Docker Compose smoke test on owner's machine (confirmed 2026-11-27).
- [x] Commit portable npm lockfile and use npm ci for reproducibility.

## B — Roles and projects
- Initial ERD and migration tool for organizations/projects/users/memberships.
- Secure authentication and project-level isolation.
- No public deployment without security review.

## C — First real Yandex connector
- Verify API requirements and access permissions.
- Read-only connector, manual ingestion, safe upserts and sync status.
- Reconcile metrics against Yandex source reports.

## D — Insight dashboard
- Real KPI cards, periods, campaign reports, freshness and goal provenance.

## E — AI Analyst + Audit Lite
- Deterministic calculation tools, bounded LLM explanations, evidence-linked rules.

## F — Pilot
- One authorized customer project, verified privacy, backups and cost caps.
