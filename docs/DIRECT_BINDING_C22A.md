# C2.2a — Project-to-Yandex Direct login mapping

## This stage's deliverable

Create a single **non-secret configuration record** mapping a MAKO
`organization_id` + `project_id` to one Yandex Direct advertiser Client-Login.
The local browser labels the record **"Логин указан · подключение не подтверждено"**.

Even though the developer application and first live agency probe are working
(377 clients and 243 campaigns in the manually selected account, 2026-11-27),
**MAKO does not yet hold or manage OAuth tokens**. There is no account access,
OAuth approval, statistics ingestion, advertiser enumeration or automatic sync
from these new project settings.

## Security rules

- API routes all require a server-verified MAKO session. Changing a binding
  requires the matching trusted frontend Origin. No caller-supplied user IDs.
- Only an organization `owner` or `admin` may read/write/remove the binding.
  Project `manager/editor/viewer` roles alone do not grant these privileges.
- Missing projects and cross-tenant IDs yield an undisclosing 404; normal
  organization members get 403. Archived projects are readable by organization
  administrators, but binding changes are blocked with 409.
- Input is limited to a Yandex Client-Login pattern and 255 characters;
  **extra OAuth token, secret or password fields are rejected** by Pydantic.
- The new PostgreSQL table has a composite tenant-project foreign key. The
  project row is locked to serialize binding modifications. Each change and
  the corresponding `project_events` row commit atomically.
- Bind, change and unlink events record actor and old/new logins, not secrets.
  Existing append-only trigger still protects history from UPDATE/DELETE.
- The login is business account metadata, **not a credential**, but must still
  be handled as client-confidential information. It exists only in the local
  PostgreSQL database and authenticated admin UI, never in public GitHub code.

## Data model

`project_direct_bindings` — `project_id` PK, `organization_id`,
`client_login`, `status=configured_unverified`, `updated_at`.

`project_events` — adds `old_client_login` and `new_client_login`, and
allowlists the `direct_bind` / `direct_unbind` actions. Existing events and
their immutable audit trigger are preserved by migration 0004.

API routes:
- `GET /organizations/{org_id}/projects/{project_id}/direct-binding` — admin-only
  current login or `not_configured`.
- `PUT` same path — create/update (body only `{"client_login":"example"}`).
- `DELETE` same path — remove mapping, preserving audit history.

Neither the API nor the dashboard accepts OAuth tokens.

## Local migration

From VS Code PowerShell:

```powershell
git pull
docker compose up --build -d
docker compose exec backend alembic -c /app/alembic.ini upgrade head
docker compose exec backend alembic -c /app/alembic.ini current
```

Expected: `0004_direct_binding (head)`.
Do **not** run `docker compose down -v` or a downgrade: downgrade loses
saved bindings and login fields from the audit history.

## C2.2b security design (implementation deliberately deferred)

Before persistent credentials or live provider endpoints:
1. Use a verified OAuth grant for the exact API-approved Yandex OAuth Client ID.
   Protect state/nonce and handle authorization errors, expiry and revocation.
2. Store access/refresh tokens **encrypted at rest with authenticated encryption**,
   with encryption keys held **outside PostgreSQL and source control** (e.g.
   a protected local secret mount / OS key store). Do not store any key or
   password in a public GitHub repository, web page, URL or audit table.
3. Define token rotation, forced reconnection, explicit disconnect and
   owner/admin access policy. Never serialize tokens to API responses or logs.
4. Prove membership/access to the selected advertiser using a server-side
   read-only agency client lookup and an authorized token before changing the
   connection state from `configured_unverified` to a verified status.
5. Add request quotas, expiry, retries, read-only allowlist and account privacy
   gates, with negative tests. Do not deploy publicly before HTTPS, secrets
   management and a professional security review.

## Cost

No extra hosting, cloud services or paid AI. Only the already-running local
PostgreSQL/Docker and GitHub Actions test runners are used. CI is offline
relative to Yandex and uses synthetic logins only.
