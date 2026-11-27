# C1 — Yandex Direct read-only adapter

Verified against the official Yandex Direct API documentation on 2026-11-27.

## Official docs and prerequisites

- JSON version **v501**: https://yandex.ru/dev/direct/doc/ru/format
- API/OAuth authorization: https://yandex.ru/dev/direct/doc/ru/concepts/auth-token
- Developer application registration + access approval:
  https://yandex.ru/dev/direct/doc/ru/access-request
- Agency clients get: https://yandex.ru/dev/direct/doc/ru/agencyclients/get
- Campaigns get: https://yandex.ru/dev/direct/doc/ru/campaigns/get
- Pagination: https://yandex.ru/dev/direct/doc/ru/best-practice/get
- Usage limits: https://yandex.ru/dev/direct/doc/ru/concepts/units
- Reports: https://yandex.ru/dev/direct/doc/ru/reports

Yandex requires an OAuth application registered by its developer and an
approved Direct API access request before live API calls. The API is free,
but governed by service quotas and daily/hourly units. Yandex documentation
describes a maximum of five simultaneous requests per advertiser; C1 runs
only sequential, manually initiated reads and caps paging.

## What this version implements

`mako_intelligence.integrations.yandex_direct.DirectReadClient` has exactly:
- `get_campaigns(client_login=None)` -> list of IDs/names from Campaigns.get.
- `get_agency_clients()` -> agency's client IDs/logins from AgencyClients.get.

The fixed host is `https://api.direct.yandex.com/json/v501`. Requests
are HTTPS POST with `method=get`, OAuth Bearer header and the optional
`Client-Login` for campaigns belonging to an agency client. AgencyClients.get
does not send Client-Login, per Yandex docs.

The adapter accepts no arbitrary service name through public methods. It
**cannot change ads, keywords, budgets, bids or campaign settings**.
Pagination follows `LimitedBy` to `Page.Offset`, capped at 10 pages
of 100 items. If this initial safety cap is exceeded, the client returns
an error rather than silently hiding further items; C2 will add scalable
incremental fetching.

It returns raw provider objects **in memory only**; no storage, HTTP exposure,
browser data, imports or syncing. Sensitive error details and response bodies
are never printed. The test suite uses only `httpx.MockTransport`, with
synthetic IDs/tokens — no network access.

## Optional local one-time probe

Only after you have **approved Direct API access** and permission to read
the chosen account, run this in VS Code:

```powershell
git pull
docker compose up --build -d
docker compose exec backend python -m mako_intelligence.tools.yandex_direct_probe
```

Choose advertiser (1) or agency (2). Agency mode asks for the login of
the client you are authorized to read. Then paste the token into the
**hidden interactive prompt**. The terminal prints counts only.

**Never** send the OAuth token into this chat, GitHub, the frontend, a URL,
an API request body, command-line flags or screenshots. Do not add it to
`.env`; the C1 proof-of-read intentionally avoids persistent secrets.

If you get a sanitized 401/403/API error, confirm app approval, the OAuth
user account, access rights and agency Client-Login before trying again.
Do not brute-force requests: quotas and Yandex rate limits apply.

## Required for C2 before real use

- Design a secure OAuth authorization/code exchange flow and revocation.
- Server-side encrypted token store and secrets/key management (never in git).
- Tenant/project linkage with explicit opt-in, scoped access and audit history.
- Safe retries/queues for 202/429 Reports responses, unit budgets and service limits.
- Time zone, currency, campaign types and conversion goals must be reconciled
  against source reports. Statistics and Reports are **not** implemented in C1.
- Protect personally identifying/client-account data and restrict deployments.

## Cost

Zero incremental infrastructure cost. Real Yandex Direct API access is
free, but quota-limited; no live calls occur until the user manually
runs the optional probe with an authorized token.

## Troubleshooting: code 58, approved app and token visibility

**Error 58 = incomplete OAuth application registration for Direct API.**
If the access request is approved, verify that the token was generated
for the **same OAuth Client ID** listed in the approved application request.
A token from another app does not inherit this application's approval.
Official reference: https://yandex.ru/dev/direct/doc/ru/concepts/errors-list

After running the probe, select input mode:
- `2` or Enter: hidden prompt (default); it shows a **character count** after pasting.
- `1`: visibly echo the token in your local terminal when explicitly needed.
  **This exposes the token** in terminal scrollback and screenshots; close the
  terminal afterward and do not share screenshots containing it.

The probe also prints the method being checked before calling it:
AgencyClients.get first for agency mode, then Campaigns.get.
When the error is 58, the probe prints a safe, actionable explanation
without echoing token, upstream errors, response body or client names.
