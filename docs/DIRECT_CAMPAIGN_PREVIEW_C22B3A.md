# C2.2b3a — On-demand read-only campaign preview

Goal: display real advertiser campaign **names and IDs** inside the existing
local project dashboard without storing an inventory or calling the provider
automatically. This does not yet include campaign statistics, budgets or CPA.

## Operation

- Organization owner/admin opens an active project already linked to an
  authorized Yandex advertiser and successfully verified through C2.2b1.
- **Показать кампании** sends one authenticated POST with matching frontend
  Origin to `/organizations/{org_id}/projects/{project_id}/direct-campaign-preview`.
- Server decrypts organization-level AES-GCM agency token and invokes only
  `Campaigns.get` for the bound `Client-Login`.
- The response contains `{"count":N,"fetched_at":"...","campaigns":[{"id":...,"name":...}]}`.
- No OAuth token, other advertiser accounts or raw provider error bodies
  are sent to the browser.
- Limit is 1000 campaigns (the underlying Direct client is bounded to ten
  pages of 100). More campaigns returns an explicit failure, not a partial list.
- Campaign names have a maximum accepted length of 255 characters. Any
  malformed provider row fails the entire response with a safe error.
- Successful results are displayed with a search field and 25-item pagination
  inside the UI; the list disappears on UI unmount or refreshing the page.
- Nothing is persisted into PostgreSQL or background jobs. Response specifies
  `Cache-Control: no-store`.

## Access and confidentiality

- Server uses MAKO cookie identity, never a supplied username.
- Only organization owners/admins can access previews, and only for an
  active project in the organization. Archived projects and unauthenticated/
  external organizations are blocked.
- Exact trusted frontend Origin required before any provider call.
- A current organization token and successful account verification from
  the last **24 hours** are required. Old or revoked login/token configuration
  fails closed with 409; users can reverify first.
- Server checks project status, configured login, verified timestamp and
  encrypted credential revision **again after** the external request, under
  DB locks, before releasing campaign names to the requester.
- Existing local token import and remove commands now invalidate ALL
  per-project verification timestamps/counts for the organization.
  This prevents reuse after a token is deleted and reimported with revision 1.
- Offline tests use fake Yandex answers; CI never connects to client accounts.

## VS Code smoke test

```powershell
git pull
docker compose up --build -d
```

No new Alembic migration. After opening `http://localhost:3000`,
select a verified, authorized test project. Click **Показать кампании**.
For the previously verified advertiser, expect about 243 campaigns (the
number can change). Search for one campaign by part of its name or ID.
Verify the same ID/name exists in Yandex Direct. Test Next/Previous paging.

## Limitations

No campaign storage, automated schedules, statistical metrics, dashboards,
real-time access guarantees, login token refresh or production deployment.
Reading campaign names is sensitive client metadata. Do not share screenshots
of client lists externally or expose the development server to public networks.
Repeated manual reloads consume Yandex Direct API quotas. Future C2.2b3b
will store tenant-scoped inventory with freshness and deletion/reconciliation.
