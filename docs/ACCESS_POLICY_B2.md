# Milestone B2.1 — permission rules (authorization kernel)

B1 is installed locally. B2.1 adds only tested authorization logic; there is **no user login, tenant data HTTP endpoint or project CRUD yet**.

## Decisions for the initial product

- An organization is the security boundary. Each project belongs to exactly one organization.
- Organization `owner` and `admin` inherit manager-level access to every project **within the same organization**, even without explicit project membership. This is a product decision that can be revisited before real clients are onboarded.
- Organization `member` has no default project access. The user must have a project_membership row.
- Project roles: `manager` (view, edit, manage members), `editor` (view, edit), `viewer` (view only).
- Archived project status suppresses edit and member-management permissions for everyone; restoration will be an explicit future admin-only flow.
- Unknown roles and statuses, missing memberships, non-existent project IDs, and cross-org IDs always **deny**.
- A future API must take `user_id` solely from a verified session, *never from an arbitrary header, query parameter or request body*.
- The empty permission result must map to a nondisclosing 404/403 policy at the API boundary. No unauthenticated project enumeration.

## Implementation and tests

`mako_intelligence.core.permissions` contains pure policy rules and tenant-scoped SQLAlchemy read queries:
- `resolve_project_actions` — no database required.
- `project_permissions(session, user_id, organization_id, project_id)` — denies absent memberships.
- `visible_projects(session, user_id, organization_id)` — lists only authorized projects in that organization.

Tests run against synthetic organizations and projects inside a rolled-back transaction on disposable PostgreSQL in GitHub Actions. They verify inherited role access, explicit project roles, archive read-only, forbidden cross-org access and scoped listings.

## Deliberate security limit

**This is necessary but not sufficient for customer-safe multi-tenancy.** HTTP authentication, session protection, CSRF handling, rate limits, tenant-aware data repositories, audit logging and an admin bootstrap process are not yet implemented. Do not deploy the current scaffold publicly.

## Next: B2.2

Select and implement a minimal secure login/session mechanism, seeded local owner (secret supplied interactively, not in git), then expose the first tenant-scoped project view only after negative authorization tests pass.

## Cost

No new database tables or migration in B2.1, no paid infrastructure, no additional libraries.
