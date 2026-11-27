# C2.2b3a.1 — Why product campaigns were missing

## Finding

Our initial `Campaigns.get` request with `FieldNames=["Id","Name"]`
returned 243 campaigns for the authorized test advertiser, but the user
noticed that some **Товарные кампании** were absent.

The Direct user interface has distinct campaign formats:
- ЕПК (`UNIFIED_CAMPAIGN`) can serve product ads as part of a unified
  campaign and is supported by the campaign management API.
- **Товарная кампания** created via Мастер кампаний is a separate product
  offering. Some formats are not enumerable via management `Campaigns.get`,
  even though Reports can contain their statistics.

The fix does NOT assert that `Campaigns.get` with extra unified fields
would produce product campaigns. An empty `SelectionCriteria` already
requests the management service's available campaign objects. A different
source is needed for reconciliation.

## Two complementary read-only sources

1. `Campaigns.get` on `/json/v501/campaigns` yields management inventory.
2. `Reports` on `/json/v501/reports` uses
   `CAMPAIGN_PERFORMANCE_REPORT`, `LAST_365_DAYS`,
   and `FieldNames=[CampaignId, CampaignName, CampaignType, Impressions]`.

Yandex Reports is read-only and responds with TSV. We request automatic
processing. HTTP 200 returns a TSV with explicit headers. HTTP 201/202
means the report is queued or not ready: **never treat it as zero campaigns**.
For 429/500 and malformed responses, the preview clearly states its report
source failed, not that campaigns are absent.

When ready, merge by CampaignId:
- API-only campaigns: source `campaigns`;
- campaigns found in both: `both`;
- only in reports: `reports` with report campaign type.
Show the source on each item and a count of additions from reports.
Keep management names as the display name for duplicate IDs, since report
names may lag a rename. Do not persist any campaign information.

## Completeness limits

The Reports source covers only the **previous 365 completed days** and only
campaigns represented in the returned statistics. It cannot prove that
an advertiser has no other product campaigns, especially never-launched,
zero-impression or older dormant ones.

A successful report is labelled **period-limited**, not `complete`.
A queued or failed report is labelled **incomplete**. This distinction
must remain when the future MAKO analytic product ingests metrics.

## Local verification

No migration and no reimport of the agency token. In VS Code:

```powershell
git pull
docker compose up --build -d
```

In the active, verified test project open Direct settings and click
**Обновить список кампаний**. Compare the old management count
(around 243 for the original snapshot) against the added report-only
campaign count, search for one missing product campaign by exact ID/name
and verify that ID against the Direct web UI.

On first attempt Reports can return queued 201/202. In this case MAKO shows
"отчёт формируется" and does not claim the inventory is full.
Refresh manually later after Yandex finishes report processing.

## Official docs

- https://yandex.ru/dev/direct/doc/ru/campaigns/get
- https://yandex.ru/dev/direct/doc/ru/objects/campaign
- https://yandex.ru/dev/direct/doc/ru/fields-list
- https://yandex.ru/dev/direct/doc/ru/period
- https://yandex.ru/dev/direct/doc/ru/mode
- https://yandex.ru/dev/direct/doc/ru/reports
- https://yandex.ru/support/direct/ru/product-campaign/create

## Safety

All requests remain read-only, bounded and tenant-scoped. Provider tokens
never enter the frontend, request body or public repository. No automatic
retries or background jobs. Offline CI uses only synthetic data.
