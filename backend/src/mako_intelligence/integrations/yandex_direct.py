"""Restricted read-only Yandex Direct API v501 adapter.

No client account or OAuth token is stored by this module. The fixed API host
and explicit allowlist prohibit ad, budget or bid modifications.

Documentation: https://yandex.ru/dev/direct/doc/ru/format
"""
from __future__ import annotations

import re
from typing import Any

import httpx

BASE_URL = "https://api.direct.yandex.com/json/v501"
PAGE_SIZE = 100
MAX_PAGES = 10
_ALLOWED_LOGIN = re.compile(r"[a-zA-Z0-9._@-]{1,255}\Z")


class DirectReadError(Exception):
    """Safe-to-display provider error, retaining only an optional numeric code."""

    def __init__(self, message: str, *, error_code: int | None = None) -> None:
        super().__init__(message)
        self.error_code = error_code


class DirectReadClient:
    """Only allows get operations on two explicitly approved Direct services.

    Supports a supplied httpx client for deterministic mocked tests.
    Constructor tokens must be entered interactively by the local caller;
    do not print or persist them.
    """

    def __init__(self, token: str, *, http_client: httpx.Client | None = None) -> None:
        if not token or any(ord(character) < 32 or ord(character) == 127 for character in token):
            raise ValueError("A valid OAuth token is required")
        self._token = token
        self._owns_client = http_client is None
        self._client = http_client or httpx.Client(
            timeout=httpx.Timeout(15.0, connect=5.0), follow_redirects=False
        )

    def __enter__(self) -> DirectReadClient:
        return self

    def __exit__(self, *_args: object) -> None:
        if self._owns_client:
            self._client.close()

    @staticmethod
    def _validate_login(client_login: str | None) -> str | None:
        if client_login is None:
            return None
        if not _ALLOWED_LOGIN.fullmatch(client_login):
            raise ValueError("Invalid Yandex Direct client login")
        return client_login

    def _request(
        self,
        *,
        service: str,
        params: dict[str, Any],
        result_field: str,
        client_login: str | None,
    ) -> dict[str, Any]:
        if (service, result_field) not in {
            ("campaigns", "Campaigns"),
            ("agencyclients", "Clients"),
        }:
            raise ValueError("Unsupported read-only Direct service")
        if service == "agencyclients" and client_login is not None:
            raise ValueError("AgencyClients.get never uses Client-Login")

        headers = {
            "Authorization": f"Bearer {self._token}",
            "Accept-Language": "ru",
        }
        if client_login is not None:
            headers["Client-Login"] = self._validate_login(client_login)

        try:
            response = self._client.post(
                f"{BASE_URL}/{service}",
                headers=headers,
                json={"method": "get", "params": params},
            )
        except httpx.RequestError:
            # HTTP errors may embed URLs or headers; do not leak raw exception text.
            raise DirectReadError("Direct API transport error") from None

        if response.status_code != 200:
            raise DirectReadError(f"Direct API HTTP status {response.status_code}")
        try:
            data = response.json()
        except ValueError:
            raise DirectReadError("Direct API returned invalid JSON") from None

        if not isinstance(data, dict):
            raise DirectReadError("Direct API returned unexpected response data")
        if "error" in data:
            raw_error = data["error"]
            code = raw_error.get("error_code") if isinstance(raw_error, dict) else None
            safe_code = code if type(code) is int else None
            code_info = f", code {safe_code}" if safe_code is not None else ""
            raise DirectReadError(
                f"Direct API rejected the request{code_info}", error_code=safe_code
            )
        result = data.get("result")
        if not isinstance(result, dict) or not isinstance(result.get(result_field), list):
            raise DirectReadError("Direct API returned unexpected result structure")
        return result

    def _pages(
        self,
        *,
        service: str,
        result_field: str,
        fields: list[str],
        client_login: str | None,
    ) -> list[dict[str, Any]]:
        items: list[dict[str, Any]] = []
        offset = 0
        for _ in range(MAX_PAGES):
            result = self._request(
                service=service,
                params={
                    "SelectionCriteria": {},
                    "FieldNames": fields,
                    "Page": {"Limit": PAGE_SIZE, "Offset": offset},
                },
                result_field=result_field,
                client_login=client_login,
            )
            batch = result[result_field]
            if not all(isinstance(entry, dict) for entry in batch):
                raise DirectReadError("Direct API returned malformed rows")
            items.extend(batch)
            limited_by = result.get("LimitedBy")
            if limited_by is None:
                return items
            if type(limited_by) is not int or limited_by <= offset:
                raise DirectReadError("Direct API pagination is inconsistent")
            offset = limited_by

        raise DirectReadError("Direct API pagination cap reached; reduce result set")

    def get_campaigns(self, *, client_login: str | None = None) -> list[dict[str, Any]]:
        """Get campaign IDs and names; agency accounts specify Client-Login."""
        self._validate_login(client_login)
        return self._pages(
            service="campaigns",
            result_field="Campaigns",
            fields=["Id", "Name"],
            client_login=client_login,
        )

    def get_agency_clients(self) -> list[dict[str, Any]]:
        """List accessible agency clients; must not send a Client-Login header."""
        return self._pages(
            service="agencyclients",
            result_field="Clients",
            fields=["ClientId", "Login", "ClientInfo"],
            client_login=None,
        )
