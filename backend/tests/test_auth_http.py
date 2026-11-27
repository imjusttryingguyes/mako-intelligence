"""HTTP integration tests: verified sessions, forbidden project access and logout.

Uses only a disposable MAKO_TEST_DATABASE_URL and synthetic records.
All inserts are rolled back after each test.
"""
from __future__ import annotations

import os
import uuid
from datetime import datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select, update
from sqlalchemy.engine import make_url
from sqlalchemy.orm import Session

from mako_intelligence.core.auth import COOKIE_NAME, hash_password
from mako_intelligence.db.models import (
    AuthSession,
    LocalCredential,
    Organization,
    OrganizationMembership,
    Project,
    ProjectMembership,
    User,
)
from mako_intelligence.db.session import get_db
from mako_intelligence.main import app

TEST_URL = os.getenv("MAKO_TEST_DATABASE_URL")
ORIGIN = "http://localhost:3000"

pytestmark = pytest.mark.skipif(not TEST_URL, reason="No disposable test database configured")


@pytest.fixture()
def api(monkeypatch):
    assert TEST_URL is not None
    assert "test" in (make_url(TEST_URL).database or "").lower()
    monkeypatch.setenv("MAKO_LOCAL_AUTH_ENABLED", "1")
    engine = create_engine(TEST_URL)
    connection = engine.connect()
    transaction = connection.begin()
    db = Session(bind=connection, join_transaction_mode="create_savepoint")
    ids = {name: uuid.uuid4() for name in (
        "org", "other_org", "owner", "member", "stranger",
        "first", "second", "archived", "other_project",
    )}
    password = "local-testing-only-secret"
    try:
        db.add_all([
            Organization(id=ids["org"], slug=f"primary-{ids['org'].hex[:10]}", name="Primary"),
            Organization(
                id=ids["other_org"], slug=f"other-{ids['other_org'].hex[:10]}", name="Other"
            ),
        ])
        db.add_all([
            User(id=ids["owner"], email=f"owner-{ids['owner'].hex}@example.invalid",
                 display_name="Owner"),
            User(id=ids["member"], email=f"member-{ids['member'].hex}@example.invalid",
                 display_name="Member"),
            User(id=ids["stranger"], email=f"other-{ids['stranger'].hex}@example.invalid",
                 display_name="Stranger"),
        ])
        db.flush()
        db.add_all([
            LocalCredential(user_id=ids[key], password_hash=hash_password(password))
            for key in ("owner", "member", "stranger")
        ])
        db.add_all([
            OrganizationMembership(
                organization_id=ids["org"], user_id=ids["owner"], role="owner"
            ),
            OrganizationMembership(
                organization_id=ids["org"], user_id=ids["member"], role="member"
            ),
            OrganizationMembership(
                organization_id=ids["other_org"], user_id=ids["stranger"], role="owner"
            ),
        ])
        db.add_all([
            Project(id=ids["first"], organization_id=ids["org"], slug="first",
                    name="First", status="active"),
            Project(id=ids["second"], organization_id=ids["org"], slug="second",
                    name="Second", status="active"),
            Project(id=ids["archived"], organization_id=ids["org"], slug="archived",
                    name="Archived", status="archived"),
            Project(
                id=ids["other_project"], organization_id=ids["other_org"],
                slug="other-project", name="Foreign", status="active",
            ),
        ])
        db.flush()
        db.add(ProjectMembership(
            project_id=ids["first"], organization_id=ids["org"], user_id=ids["member"],
            role="viewer",
        ))
        db.flush()

        def override_db():
            yield db

        app.dependency_overrides[get_db] = override_db
        with TestClient(app) as client:
            yield client, db, ids, password
    finally:
        app.dependency_overrides.pop(get_db, None)
        db.close()
        transaction.rollback()
        connection.close()
        engine.dispose()


def sign_in(client: TestClient, email: str, password: str):
    return client.post(
        "/auth/login", json={"email": email, "password": password},
        headers={"Origin": ORIGIN},
    )


def test_unauthenticated_endpoints_reject_requests(api) -> None:
    client, _db, ids, _pw = api
    for route in (
        "/auth/me",
        "/organizations",
        f"/organizations/{ids['org']}/projects",
        f"/organizations/{ids['org']}/projects/{ids['first']}",
    ):
        assert client.get(route).status_code == 401


def test_missing_or_foreign_origin_is_denied(api) -> None:
    client, db, ids, password = api
    email = db.get(User, ids["owner"]).email
    for headers in ({}, {"Origin": "https://attacker.example"}):
        response = client.post(
            "/auth/login", json={"email": email, "password": password}, headers=headers,
        )
        assert response.status_code == 403
    assert not client.cookies.get(COOKIE_NAME)


def test_invalid_credentials_do_not_issue_session(api) -> None:
    client, db, ids, password = api
    email = db.get(User, ids["owner"]).email
    assert sign_in(client, email, password + "-wrong").status_code == 401
    assert sign_in(client, "unknown@example.invalid", password).status_code == 401
    assert client.get("/auth/me").status_code == 401


def test_cookie_authentication_and_logout_revoke_session(api) -> None:
    client, db, ids, password = api
    email = db.get(User, ids["owner"]).email
    response = sign_in(client, email.upper(), password)
    assert response.status_code == 200
    assert response.json()["id"] == str(ids["owner"])
    cookie = response.headers["set-cookie"].lower()
    assert "httponly" in cookie and "samesite=strict" in cookie
    assert client.get("/auth/me").json()["display_name"] == "Owner"
    assert client.post("/auth/logout").status_code == 403
    assert client.get("/auth/me").status_code == 200
    assert client.post("/auth/logout", headers={"Origin": ORIGIN}).status_code == 204
    assert client.get("/auth/me").status_code == 401


def test_owner_sees_only_own_organization_projects(api) -> None:
    client, db, ids, password = api
    assert sign_in(client, db.get(User, ids["owner"]).email, password).status_code == 200
    organizations = client.get("/organizations").json()
    assert [org["id"] for org in organizations] == [str(ids["org"])]
    project_list = client.get(f"/organizations/{ids['org']}/projects")
    assert project_list.status_code == 200
    assert {p["id"] for p in project_list.json()} == {
        str(ids["first"]), str(ids["second"]), str(ids["archived"]),
    }
    archived = client.get(
        f"/organizations/{ids['org']}/projects/{ids['archived']}"
    )
    assert archived.status_code == 200
    assert archived.json()["actions"] == ["view"]
    forbidden = client.get(
        f"/organizations/{ids['other_org']}/projects/{ids['other_project']}"
    )
    assert forbidden.status_code == 404
    assert client.get(f"/organizations/{ids['other_org']}/projects").status_code == 404


def test_project_member_cannot_enumerate_unassigned_projects(api) -> None:
    client, db, ids, password = api
    assert sign_in(client, db.get(User, ids["member"]).email, password).status_code == 200
    project_list = client.get(f"/organizations/{ids['org']}/projects")
    assert [project["id"] for project in project_list.json()] == [str(ids["first"])]
    assert project_list.json()[0]["actions"] == ["view"]
    assert client.get(
        f"/organizations/{ids['org']}/projects/{ids['second']}"
    ).status_code == 404
    assert client.get(
        f"/organizations/{ids['org']}/projects/{ids['first']}"
    ).status_code == 200


def test_expired_cookie_is_rejected(api) -> None:
    client, db, ids, password = api
    assert sign_in(client, db.get(User, ids["owner"]).email, password).status_code == 200
    db.execute(
        update(AuthSession).where(AuthSession.user_id == ids["owner"]).values(
            expires_at=datetime.now(timezone.utc) - timedelta(seconds=30),
        )
    )
    db.flush()
    assert client.get("/auth/me").status_code == 401
    assert client.get("/organizations").status_code == 401


def test_local_auth_requires_explicit_enablement(api, monkeypatch) -> None:
    client, db, ids, password = api
    monkeypatch.delenv("MAKO_LOCAL_AUTH_ENABLED")
    response = sign_in(client, db.get(User, ids["owner"]).email, password)
    assert response.status_code == 503
    assert not db.scalar(select(AuthSession.user_id).limit(1))
