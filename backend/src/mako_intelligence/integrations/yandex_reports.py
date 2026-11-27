"""Bounded, read-only Yandex Direct Reports API campaign reconciliation.

Campaigns.get alone does not reliably enumerate all campaign types visible in
the Direct UI, especially some Campaign Master formats. Reports contains only
campaigns with statistics for the requested period, NOT a complete catalog.

A queued report (HTTP 201/202) is never silently treated as an empty report.
The caller can retry later; no server-side busy loop or background job.
"""
from __future__ import annotations

import csv
import io
import re
from dataclasses import dataclass

import httpx

from mako_intelligence.integrations.yandex_direct import DirectReadError

REPORTS_URL = "https://api.direct.yandex.com/json/v501/reports"
REPORT_PERIOD = "LAST_365_DAYS"
REPORT_FIELDS = ("CampaignId", "CampaignName", "CampaignType", "Impressions")
MAX_TSV_BYTES = 4_000_000
MAX_REPORT_ROWS = 10_000
LOGIN_RE = re.compile(r"[a-zA-Z0-9._@-]{1,255}\Z")


@dataclass(frozen=True)
class CampaignReport:
    status: str  # "ready" or "pending"
    campaigns: list[dict]
    period: str = REPORT_PERIOD


def parse_campaign_report(tsv: str) -> list[dict]:
    """Parse a report with a column header and no summary/footer rows."""
    if not tsv.strip():
        return []
    reader = csv.DictReader(io.StringIO(tsv.lstrip("\ufeff"), newline=""), delimiter="\t")
    if reader.fieldnames is None or tuple(reader.fieldnames) != REPORT_FIELDS:
        raise DirectReadError("Direct Reports unexpected TSV columns")
    results: dict[int, dict] = {}
    for count, row in enumerate(reader, start=1):
        if count > MAX_REPORT_ROWS:
            raise DirectReadError("Direct Reports row limit exceeded")
        if None in row or any(row.get(field) is None for field in REPORT_FIELDS):
            raise DirectReadError("Direct Reports malformed TSV rows")
        try:
            campaign_id = int(row["CampaignId"])
        except (ValueError, TypeError):
            raise DirectReadError("Direct Reports invalid campaign ID") from None
        campaign_name = row["CampaignName"]
        campaign_type = row["CampaignType"]
        if (
            campaign_id <= 0 or campaign_id > 2**63 - 1
            or not campaign_name or len(campaign_name) > 255
            or not campaign_type or len(campaign_type) > 100
        ):
            raise DirectReadError("Direct Reports invalid campaign details")
        if campaign_id in results:
            existing = results[campaign_id]
            if existing["name"] != campaign_name or existing["type"] != campaign_type:
                raise DirectReadError("Direct Reports inconsistent campaign identity")
            continue
        results[campaign_id] = {
            "id": campaign_id,
            "name": campaign_name,
            "type": campaign_type,
        }
    return list(results.values())


class DirectReportsClient:
    def __init__(self, token: str, *, http_client: httpx.Client | None = None) -> None:
        if not token or any(ord(ch) < 32 or ord(ch) == 127 for ch in token):
            raise ValueError("A valid OAuth token is required")
        self._token = token
        self._owns_client = http_client is None
        self._client = http_client or httpx.Client(
            timeout=httpx.Timeout(30.0, connect=5.0), follow_redirects=False
        )

    def __enter__(self) -> DirectReportsClient:
        return self

    def __exit__(self, *_args: object) -> None:
        if self._owns_client:
            self._client.close()

    def get_campaigns_with_statistics(self, *, client_login: str) -> CampaignReport:
        if not LOGIN_RE.fullmatch(client_login):
            raise ValueError("Invalid Yandex Direct client login")
        payload = {
            "params": {
                "SelectionCriteria": {},
                "FieldNames": list(REPORT_FIELDS),
                "ReportName": "MAKO-CampaignInventory-365d-v1",
                "ReportType": "CAMPAIGN_PERFORMANCE_REPORT",
                "DateRangeType": REPORT_PERIOD,
                "Format": "TSV",
                "IncludeVAT": "NO",
                "IncludeDiscount": "NO",
            }
        }
        try:
            response = self._client.post(
                REPORTS_URL,
                headers={
                    "Authorization": f"Bearer {self._token}",
                    "Client-Login": client_login,
                    "Accept-Language": "ru",
                    "processingMode": "auto",
                    "skipReportHeader": "true",
                    "skipReportSummary": "true",
                },
                json=payload,
            )
        except httpx.RequestError:
            raise DirectReadError("Direct Reports transport error") from None
        if response.status_code in (201, 202):
            return CampaignReport(status="pending", campaigns=[])
        if response.status_code != 200:
            raise DirectReadError(f"Direct Reports HTTP status {response.status_code}")
        if len(response.content) > MAX_TSV_BYTES:
            raise DirectReadError("Direct Reports response size limit exceeded")
        try:
            parsed = parse_campaign_report(response.content.decode("utf-8-sig"))
        except UnicodeDecodeError:
            raise DirectReadError("Direct Reports invalid text encoding") from None
        return CampaignReport(status="ready", campaigns=parsed)
