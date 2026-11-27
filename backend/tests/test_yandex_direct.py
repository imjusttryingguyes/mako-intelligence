"""Offline-only provider contract tests, no network or real credentials."""
from __future__ import annotations

import json

import httpx
import pytest

from mako_intelligence.integrations.yandex_direct import (
    BASE_URL,
    MAX_PAGES,
    PAGE_SIZE,
    DirectReadClient,
    DirectReadError,
)


def test_advertiser_campaign_read_matches_current_yandex_v501_contract() -> None:
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(
            200, json={"result": {"Campaigns": [{"Id": 123, "Name": "Test"}]}}
        )

    with httpx.Client(transport=httpx.MockTransport(handler)) as http:
        with DirectReadClient("fixture-token-not-real", http_client=http) as client:
            assert client.get_campaigns() == [{"Id": 123, "Name": "Test"}]

    request = requests[0]
    assert request.method == "POST"
    assert str(request.url) == f"{BASE_URL}/campaigns"
    assert request.headers["Authorization"] == "Bearer fixture-token-not-real"
    assert request.headers["Accept-Language"] == "ru"
    assert "Client-Login" not in request.headers
    data = json.loads(request.content)
    assert data["method"] == "get"
    assert data["params"]["FieldNames"] == ["Id", "Name"]
    assert data["params"]["SelectionCriteria"] == {}
    assert data["params"]["Page"] == {"Limit": PAGE_SIZE, "Offset": 0}


def test_agency_campaign_read_passes_client_login_only_in_headers() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.headers["Client-Login"] == "client-example"
        assert "client-example" not in request.content.decode("utf-8")
        return httpx.Response(200, json={"result": {"Campaigns": []}})

    with httpx.Client(transport=httpx.MockTransport(handler)) as http:
        client = DirectReadClient("fake-token", http_client=http)
        assert client.get_campaigns(client_login="client-example") == []


def test_agency_client_listing_does_not_send_client_login() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert str(request.url) == f"{BASE_URL}/agencyclients"
        assert "Client-Login" not in request.headers
        assert json.loads(request.content)["method"] == "get"
        assert json.loads(request.content)["params"]["FieldNames"] == [
            "ClientId", "Login", "ClientInfo"
        ]
        return httpx.Response(
            200, json={"result": {"Clients": [{"ClientId": 20, "Login": "abc"}]}}
        )

    with httpx.Client(transport=httpx.MockTransport(handler)) as http:
        client = DirectReadClient("fake-token", http_client=http)
        assert client.get_agency_clients() == [{"ClientId": 20, "Login": "abc"}]


def test_result_pagination_uses_limited_by_as_next_offset() -> None:
    offsets: list[int] = []

    def handler(request: httpx.Request) -> httpx.Response:
        offset = json.loads(request.content)["params"]["Page"]["Offset"]
        offsets.append(offset)
        if offset == 0:
            return httpx.Response(
                200, json={"result": {"Campaigns": [{"Id": 1}], "LimitedBy": 100}}
            )
        assert offset == 100
        return httpx.Response(200, json={"result": {"Campaigns": [{"Id": 2}]}})

    with httpx.Client(transport=httpx.MockTransport(handler)) as http:
        client = DirectReadClient("fake-token", http_client=http)
        assert client.get_campaigns() == [{"Id": 1}, {"Id": 2}]
    assert offsets == [0, 100]


def test_pagination_cap_raises_instead_of_silently_dropping_accounts() -> None:
    calls = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        offset = json.loads(request.content)["params"]["Page"]["Offset"]
        return httpx.Response(
            200, json={"result": {"Campaigns": [], "LimitedBy": offset + PAGE_SIZE}}
        )

    with httpx.Client(transport=httpx.MockTransport(handler)) as http:
        client = DirectReadClient("fake-token", http_client=http)
        with pytest.raises(DirectReadError, match="pagination cap"):
            client.get_campaigns()
    assert calls == MAX_PAGES


def test_invalid_pagination_cannot_loop_forever() -> None:
    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"result": {"Campaigns": [], "LimitedBy": 0}})

    with httpx.Client(transport=httpx.MockTransport(handler)) as http:
        with pytest.raises(DirectReadError, match="pagination is inconsistent"):
            DirectReadClient("fake-token", http_client=http).get_campaigns()


@pytest.mark.parametrize(
    "login", ["", "contains space", "bad\rlogin", "bad\nlogin", "../../api", "❌"]
)
def test_untrusted_client_login_is_rejected_before_network_request(login: str) -> None:
    def handler(_request: httpx.Request) -> httpx.Response:
        raise AssertionError("Network should not be used")

    with httpx.Client(transport=httpx.MockTransport(handler)) as http:
        with pytest.raises(ValueError, match="Invalid Yandex"):
            DirectReadClient("fake-token", http_client=http).get_campaigns(client_login=login)


def test_invalid_token_controls_are_rejected_before_request() -> None:
    with pytest.raises(ValueError):
        DirectReadClient("bad\r\ntoken")
    with pytest.raises(ValueError):
        DirectReadClient("")


def test_denies_unsupported_or_mutating_services() -> None:
    def handler(_request: httpx.Request) -> httpx.Response:
        raise AssertionError("No request should be sent")

    with httpx.Client(transport=httpx.MockTransport(handler)) as http:
        client = DirectReadClient("fake-token", http_client=http)
        with pytest.raises(ValueError, match="Unsupported"):
            client._request(
                service="campaigns",
                params={"FieldNames": ["Id"]},
                result_field="Ads",
                client_login=None,
            )
        with pytest.raises(ValueError, match="Unsupported"):
            client._request(
                service="ads",
                params={"SelectionCriteria": {}},
                result_field="Ads",
                client_login=None,
            )
        with pytest.raises(ValueError, match="never uses Client-Login"):
            client._request(
                service="agencyclients",
                params={},
                result_field="Clients",
                client_login="agency-account",
            )


def test_api_error_response_never_leaks_server_body_or_token() -> None:
    token = "sensitive-secret-never-print"
    body_secret = "a-server-side-secret"

    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={"error": {"error_code": 152, "error_detail": body_secret}},
        )

    with httpx.Client(transport=httpx.MockTransport(handler)) as http:
        with pytest.raises(DirectReadError) as error:
            DirectReadClient(token, http_client=http).get_campaigns()
    assert "152" in str(error.value)
    assert token not in str(error.value)
    assert body_secret not in str(error.value)


@pytest.mark.parametrize(
    "status", [202, 301, 400, 401, 403, 429, 500, 503]
)
def test_non_200_response_fails_without_echoing_sensitive_body(status: int) -> None:
    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(status, text="SECRET FROM UPSTREAM")

    with httpx.Client(transport=httpx.MockTransport(handler)) as http:
        with pytest.raises(DirectReadError) as error:
            DirectReadClient("fake-token", http_client=http).get_campaigns()
    assert str(status) in str(error.value)
    assert "SECRET" not in str(error.value)


def test_transport_error_never_contains_connection_details() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("sensitive-proxy-info", request=request)

    with httpx.Client(transport=httpx.MockTransport(handler)) as http:
        with pytest.raises(DirectReadError) as error:
            DirectReadClient("fake-token", http_client=http).get_campaigns()
    assert "sensitive-proxy-info" not in str(error.value)


@pytest.mark.parametrize("payload", [
    {"result": {"Campaigns": "not-an-array"}},
    {"result": {}},
    {"Campaigns": []},
    [],
    {"result": {"Campaigns": [1]}},
])
def test_malformed_response_fails_closed(payload: object) -> None:
    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=payload)

    with httpx.Client(transport=httpx.MockTransport(handler)) as http:
        with pytest.raises(DirectReadError):
            DirectReadClient("fake-token", http_client=http).get_campaigns()


def test_invalid_json_is_redacted() -> None:
    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, content=b"NOT JSON SECRET")

    with httpx.Client(transport=httpx.MockTransport(handler)) as http:
        with pytest.raises(DirectReadError, match="invalid JSON"):
            DirectReadClient("fake-token", http_client=http).get_campaigns()


def test_client_does_not_close_injected_http_transport() -> None:
    with httpx.Client(transport=httpx.MockTransport(
        lambda _request: httpx.Response(200, json={"result": {"Campaigns": []}})
    )) as http:
        with DirectReadClient("fake-token", http_client=http) as direct:
            assert direct.get_campaigns() == []
        assert not http.is_closed
