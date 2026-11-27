"""Interactive token lifecycle tests without live Yandex traffic."""
from __future__ import annotations

import builtins
import getpass

import pytest
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from sqlalchemy import select

from mako_intelligence.db.models import OrganizationDirectCredential
from mako_intelligence.integrations.direct_vault import DirectVault
from test_auth_http import api as api  # Reuse the disposable PostgreSQL fixture.

from mako_intelligence.tools import direct_credentials


def test_authorized_owner_password_is_required(api, monkeypatch) -> None:
    _client, db, ids, _password = api
    # Local bootstrap's organization slug is random but loaded from DB.
    from mako_intelligence.db.models import Organization, User

    org = db.get(Organization, ids["org"])
    user = db.get(User, ids["owner"])
    answers = iter([org.slug, user.email])
    monkeypatch.setattr(builtins, "input", lambda _prompt: next(answers))
    monkeypatch.setattr(getpass, "getpass", lambda _prompt: "wrong password")
    with pytest.raises(ValueError, match="Неверные данные"):
        direct_credentials.authorized_organization(db)


def test_import_rotate_and_remove_are_encrypted_and_explicit(api, monkeypatch) -> None:
    _client, db, ids, _password = api
    from mako_intelligence.db.models import Organization

    org = db.get(Organization, ids["org"])
    key = AESGCM.generate_key(bit_length=256)
    vault = DirectVault(key)
    sample_token = "FAKE-LOCAL-AGENCY-TOKEN-NOT-REAL"

    class FakeProvider:
        def __init__(self, token: str):
            assert token == sample_token

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return None

        def get_agency_clients(self):
            return [{"Login": "fake-advertiser"}]

    monkeypatch.setattr(direct_credentials, "DirectReadClient", FakeProvider)
    monkeypatch.setattr(direct_credentials, "prompt_for_token", lambda: sample_token)
    direct_credentials.import_token(db, org, vault)
    record = db.get(OrganizationDirectCredential, ids["org"])
    assert record is not None
    assert record.revision == 1
    assert sample_token.encode() not in record.encrypted_token
    assert vault.open(record.encrypted_token, org.id) == sample_token

    direct_credentials.import_token(db, org, vault)
    db.expire_all()
    record = db.get(OrganizationDirectCredential, org.id)
    assert record.revision == 2

    monkeypatch.setattr(builtins, "input", lambda _prompt: "not-matching")
    with pytest.raises(ValueError, match="отменено"):
        direct_credentials.remove_token(db, org)
    assert db.get(OrganizationDirectCredential, org.id) is not None

    monkeypatch.setattr(builtins, "input", lambda _prompt: org.slug)
    direct_credentials.remove_token(db, org)
    assert db.scalar(
        select(OrganizationDirectCredential).where(
            OrganizationDirectCredential.organization_id == org.id
        )
    ) is None


def test_cli_never_accepts_token_as_command_argument(monkeypatch) -> None:
    monkeypatch.setattr(direct_credentials.sys, "argv", ["direct_credentials", "import", "TOKEN"])
    with pytest.raises(SystemExit, match="no token/password arguments"):
        direct_credentials.main()
