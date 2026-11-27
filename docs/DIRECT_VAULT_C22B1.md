# C2.2b1 — Encrypted manual agency token and verified advertiser access

**Scope:** local Docker on a trusted workstation only. This is **not**
production OAuth, cloud key management or a completed ongoing sync.

## Design

- One **agency token per MAKO organization** serves multiple explicitly
  configured project-to-advertiser logins. Each project remains tenant-scoped.
- The only credential input is a locally executed CLI behind a MAKO owner/admin
  username/password check. The token is never accepted by HTTP API, browser,
  repository, environment variables, CLI arguments, or audit logs.
- The CLI first checks the token with Yandex `AgencyClients.get`, then uses
  a random nonce and **AES-256-GCM** authenticated encryption. The database
  holds only a versioned ciphertext, nonce and key revision.
- The key is generated and stored in a **separate Docker named volume**,
  readable by the non-root backend group and not mounted into PostgreSQL or
  the frontend. The key is **not in Git, .env, or the database**.
- Encryption binds ciphertext to `organization_id` as authenticated data.
  Copying encrypted tokens between tenants fails decryption.
- A key is generated only by an explicit privileged one-time command.
  Existing keys are never silently overwritten by Docker redeployments.
- Manual import/rotate increments token revision. Any old successful
  project verification is immediately treated as unverified when the
  revision changes or the advertiser login changes.
- Manual token removal deletes local ciphertext; external OAuth revocation
  still requires action at Yandex.

## Verification endpoint

`POST /organizations/{org}/projects/{project}/direct-verify`:

1. Authenticated MAKO **organization owner/admin**, exact frontend Origin,
   active project and configured client login.
2. Decrypt token **server-side** after reading vault key.
3. Call `AgencyClients.get` with no Client-Login header.
4. Require the configured advertiser login to be present in the agency
   client's returned `Login` fields (case-insensitive comparison).
5. Call `Campaigns.get` for that login using the `Client-Login` header.
6. Return only latest check timestamp and campaign count; store no names,
   budgets, ads, metrics, or full agency client list.
7. Verify project/login/token revision still match before committing result.

A successful check means **last known successful access**, not permanent
authorization or background connectivity. Yandex can revoke access at any
time. A 60-second per-project verification cache reduces accidental repeated
API calls, but this is not a production-grade distributed rate limiter.

Yandex docs:
- https://yandex.ru/dev/direct/doc/ru/format
- https://yandex.ru/dev/direct/doc/ru/agencyclients/get
- https://yandex.ru/dev/direct/doc/ru/campaigns/get
- https://yandex.ru/dev/direct/doc/ru/concepts/units

## Setup in VS Code / PowerShell

```powershell
git pull
docker compose up --build -d
docker compose exec backend alembic -c /app/alembic.ini upgrade head
docker compose exec backend alembic -c /app/alembic.ini current
docker compose exec --user root backend python -m mako_intelligence.tools.init_direct_key
docker compose exec backend python -m mako_intelligence.tools.direct_credentials import
```

Expected migration: `0005_direct_vault (head)`.

Initialization must be executed **as root**, but the app and token import run
as the existing unprivileged `mako` user. Initialization prints no secret.

Interactive import prompts for:
1. Organization code, usually `mako`.
2. Local MAKO owner/admin email and password.
3. OAuth token input choice: prefer **hidden mode 2**. The prompt shows the
   character count after paste. Visible mode 1 is only for debugging a private
   terminal and exposes the token in screen recordings.
4. The command checks agency access and shows an aggregate client count.

To revoke local storage:

```powershell
docker compose exec backend python -m mako_intelligence.tools.direct_credentials remove
```

Then revoke the Yandex-issued token independently in the Yandex OAuth UI if
access must end immediately. A local removal alone does not invalidate the
external OAuth token.

## Security boundaries and cautions

- **Never** share actual tokens, encryption keys, database backups, command
  output containing sensitive logins, or client data in GitHub or chat.
- `docker compose down -v` destroys **both** database and key volumes.
- The encryption key must be kept available together with the database.
  Losing the key makes saved tokens undecryptable; replacing it silently
  is forbidden. Plan backups before real client data.
- Database and key volumes are separate, but any user with Docker admin
  access can access both. This does not protect against a compromised host.
- No production HTTPS, OAuth authorization-code + refresh, independently
  rotated key manager, centralized immutable audit, client consent workflow,
  distributed rate limits, or incident response exists yet.
- Only synthetic tests run in CI. No OAuth credentials enter GitHub Actions.
- The local test can use an advertiser account you are explicitly authorized
  to inspect; do not deploy MAKO publicly or ingest customer statistics yet.

## Troubleshooting

- 503 from verify: missing unreadable key. Initialize the key once and check
  key volume permissions. Do **not** generate a replacement over an existing key.
- 409: unbound project, no agency credential, archived project or concurrent
  changes. Confirm the client login and import token.
- 403: client login missing from accessible agency clients or insufficient
  MAKO privileges.
- 502: provider request rejected. Token may have expired, been revoked, or
  Yandex quotas/network may block calls. Check only sanitized numeric code.
- Successful verification shows count/time; no ad account data is ever
  returned wholesale in this milestone.
