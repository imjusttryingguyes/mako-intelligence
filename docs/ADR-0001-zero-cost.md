# ADR-0001: cost-first architecture (2026-11-27)

**Decision:** Start MAKO Intelligence as a local-only modular monolith.

## In scope now
- Free/open-source tools: FastAPI, Next.js, PostgreSQL, Docker Compose.
- Public GitHub repository with standard Ubuntu GitHub-hosted Actions: free CI.
- Synthetic test data only. No secrets, OAuth tokens, client exports or production data in GitHub/CI.
- No domain, VPS, managed DB, Redis, task queue, monitoring SaaS or paid LLM calls yet.

## Deliberately deferred
- Production deployment, customer login, role management and audit trails (Milestone B onwards).
- OAuth/API data ingestion (Milestone C, after permissions and legal checks).
- Redis and background workers: use PostgreSQL-backed jobs initially if appropriate, add queue only when necessary.
- LLM provider: optional adapter and per-project cost caps, after verified deterministic statistics.
- ML/synthetic conversions: only after baseline truth data and experiment design.

## Public repo security
- .env and sensitive file patterns ignored; **check manually** before every push.
- Use read-only GITHUB_TOKEN permissions in CI; no repository secrets in CI.
- Do not run pull_request_target with untrusted code or add self-hosted runners to a public repo.
- Do not deploy a customer-facing service from this scaffold: authentication and data isolation are not implemented yet.
- Git history retains accidentally committed secrets: rotation and removal procedures are required; .gitignore alone is insufficient.

## Cost gates
1. Local app + test suite: **0 recurring project infrastructure cost**.
2. First real API connector: free API limits validated; no production environment required.
3. Live pilot: choose appropriate hosting based on data residency, backups and security; separately approve spending.
4. AI integration: implement usage limits before enabling billed tokens.

**Caveat:** Developer time, electricity, any applicable local Docker Desktop licensing, and eventual hosting/API expenses are not included in the zero-rouble infrastructure estimate.
