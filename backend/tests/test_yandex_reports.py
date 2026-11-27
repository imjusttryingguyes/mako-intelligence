"""Mock-only tests for Direct Reports campaign coverage and TSV parsing."""
from __future__ import annotations

import httpx
import pytest

from mako_intelligence.integrations.yandex_direct import DirectReadError
from mako_intelligence.integrations.yandex_reports import (
    REPORT_FIELDS,
    REPORT_PERIOD,
    REPORTS_URL,
    DirectReportsClient,
    parse_campaign_report,
)


def test_reports_request_matches_read_only_yandex_contract() -> None:
    seen: list[httpx.Request] = []
    def handle(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(200, text=(
            "CampaignId\tCampaignName\tCampaignType\tImpressions\n"
            "123\tТоварная кампания\tCAMPAIGN_MASTER\t4\n"
            "456\tОбычная\tUNIFIED_CAMPAIGN\t25\n"
        ))
    with httpx.Client(transport=httpx.MockTransport(handle)) as http:
        with DirectReportsClient("FAKE-NOT-REAL", http_client=http) as direct:
            report = direct.get_campaigns_with_statistics(client_login="client-example")
    assert report.status == "ready"
    assert report.period == "LAST_365_DAYS"
    assert report.campaigns == [
        {"id": 123, "name": "Товарная кампания", "type": "CAMPAIGN_MASTER"},
        {"id": 456, "name": "Обычная", "type": "UNIFIED_CAMPAIGN"},
    ]
    request = seen[0]
    assert request.method == "POST"
    assert str(request.url) == REPORTS_URL
    assert request.headers["Authorization"] == "Bearer FAKE-NOT-REAL"
    assert request.headers["Client-Login"] == "client-example"
    assert request.headers["processingMode"] == "auto"
    assert request.headers["skipReportHeader"] == "true"
    assert request.headers["skipReportSummary"] == "true"
    body = __import__("json").loads(request.content)
    assert body.keys() == {"params"}
    params = body["params"]
    assert params["SelectionCriteria"] == {}
    assert params["FieldNames"] == list(REPORT_FIELDS)
    assert params["ReportType"] == "CAMPAIGN_PERFORMANCE_REPORT"
    assert params["DateRangeType"] == REPORT_PERIOD
    assert params["Format"] == "TSV"
    assert "method" not in body
    assert "direct:api" not in str(body)


@pytest.mark.parametrize("status", [201, 202])
def test_offline_report_queue_is_pending_not_an_empty_success(status: int) -> None:
    with httpx.Client(transport=httpx.MockTransport(
        lambda _r: httpx.Response(status, text="queued")
    )) as http:
        report = DirectReportsClient(
            "FAKE-NOT-REAL", http_client=http,
        ).get_campaigns_with_statistics(client_login="client-example")
    assert report.status == "pending"
    assert report.campaigns == []


@pytest.mark.parametrize("status", [400, 401, 403, 429, 500, 502])
def test_upstream_errors_are_redacted(status: int) -> None:
    token = "SECRET-NEVER-PRINT"
    with httpx.Client(transport=httpx.MockTransport(
        lambda _r: httpx.Response(status, text=f"BAD RESPONSE {token}")
    )) as http:
        with pytest.raises(DirectReadError) as error:
            DirectReportsClient(token, http_client=http).get_campaigns_with_statistics(
                client_login="client-example"
            )
    assert str(status) in str(error.value)
    assert token not in str(error.value)
    assert "BAD RESPONSE" not in str(error.value)


def test_tsv_parser_handles_quotes_cyrillic_duplicate_identity_and_tabs() -> None:
    tsv = (
        "CampaignId\tCampaignName\tCampaignType\tImpressions\n"
        '25\t"Товар\tкаталог"\tCAMPAIGN_MASTER\t20\n'
        '25\t"Товар\tкаталог"\tCAMPAIGN_MASTER\t4\n'
        '51\t"Покупка ""товаров"""\tUNIFIED_CAMPAIGN\t100\n'
    )
    assert parse_campaign_report(tsv) == [
        {"id": 25, "name": "Товар\tкаталог", "type": "CAMPAIGN_MASTER"},
        {"id": 51, "name": 'Покупка "товаров"', "type": "UNIFIED_CAMPAIGN"},
    ]


def test_tsv_parser_rejects_inconsistent_duplicate_campaigns() -> None:
    with pytest.raises(DirectReadError, match="inconsistent"):
        parse_campaign_report(
            "CampaignId\tCampaignName\tCampaignType\tImpressions\n"
            "21\tТовар\tA\t1\n21\tИное название\tA\t1\n"
        )


@pytest.mark.parametrize("body", [
    "CampaignId\tCampaignName\n1\tSample",
    "CampaignId\tCampaignName\tCampaignType\tImpressions\n1\tTest\tType",
    "CampaignId\tCampaignName\tCampaignType\tImpressions\ninvalid\tTest\tType\t1",
    "CampaignId\tCampaignName\tCampaignType\tImpressions\n-1\tTest\tType\t1",
    "CampaignId\tCampaignName\tCampaignType\tImpressions\n1\t\tType\t1",
    "CampaignId\tCampaignName\tCampaignType\tImpressions\n1\tTest\t\t1",
])
def test_malformed_report_rejected(body: str) -> None:
    with pytest.raises(DirectReadError):
        parse_campaign_report(body)


def test_tsv_caps_row_count_and_response_size() -> None:
    tsv = (
        "CampaignId\tCampaignName\tCampaignType\tImpressions\n"
        + "".join(f"{number}\tTest\tTYPE\t1\n" for number in range(1, 10002))
    )
    with pytest.raises(DirectReadError, match="row limit"):
        parse_campaign_report(tsv)
    huge = (
        "CampaignId\tCampaignName\tCampaignType\tImpressions\n"
        + "x" * 4_000_001
    )
    with httpx.Client(transport=httpx.MockTransport(
        lambda _r: httpx.Response(200, text=huge)
    )) as http:
        with pytest.raises(DirectReadError, match="size limit"):
            DirectReportsClient(
                "FAKE-NOT-REAL", http_client=http
            ).get_campaigns_with_statistics(client_login="client-example")


@pytest.mark.parametrize("login", ["", "bad login", "../evil", "newline\nX", "❌"])
def test_invalid_login_rejected_before_any_network_call(login: str) -> None:
    def handle(_request: httpx.Request) -> httpx.Response:
        pytest.fail("invalid login must not reach provider")
    with httpx.Client(transport=httpx.MockTransport(handle)) as http:
        with pytest.raises(ValueError):
            DirectReportsClient("FAKE-NOT-REAL", http_client=http).get_campaigns_with_statistics(
                client_login=login
            )


def test_http_transport_errors_do_not_echo_proxy_details() -> None:
    def handle(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("SENSITIVE-PROXY-URL", request=request)
    with httpx.Client(transport=httpx.MockTransport(handle)) as http:
        with pytest.raises(DirectReadError) as err:
            DirectReportsClient("FAKE-NOT-REAL", http_client=http).get_campaigns_with_statistics(
                client_login="client-example"
            )
    assert "SENSITIVE-PROXY-URL" not in str(err.value)
