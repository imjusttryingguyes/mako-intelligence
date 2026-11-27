# MAKO Intelligence — MVP product scope

MAKO Intelligence is an AI-enabled performance-marketing platform built from scratch, with a client-facing space for business owners/marketers and a professional workspace for agency specialists.

## Planned modules
1. Core — projects, users, data storage, integrations and access control.
2. Insight — Yandex Direct/Metrica statistics, trends, KPI dashboards and AI questions backed by deterministic calculations.
3. Audit — evidence-based quick account audit, issues and priorities.
4. Optimizer — deep campaign/query/placement diagnosis, suggested changes, human-approved actions.
5. Experiments — landing-page hypotheses, personalization recommendations and A/B-test outcomes.
6. Signal — ML models for qualified-lead propensity; *validated* synthetic goal signals and controlled experiments.

## Milestone A now
- Local FastAPI, Next.js and PostgreSQL with Docker Compose
- Health/readiness probes, simple metric helpers and tests
- GitHub Actions with read-only permissions and no paid third-party services
- Synthetic data only; no customer data or real account tokens
- No deployment or login yet

## Delivery principles
- Build together with AI assistance, one testable milestone at a time.
- A language model cannot invent financial statistics; calculations and sources remain deterministic/auditable.
- First paid cloud resources only after an explicit cost gate.
- Public code does not contain proprietary customer datasets, auth tokens, or trained models.
- Before first real pilot: tenant isolation, consent/legal checks, least-privilege credentials, backup strategy, audit logs, operational monitoring.
