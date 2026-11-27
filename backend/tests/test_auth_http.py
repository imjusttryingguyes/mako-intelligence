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
from sqlalchemy import create_engine, delete, select, update
from sqlalchemy.engine import make_url
from sqlalchemy.exc import DBAPIError
from sqlalchemy.orm import Session

from mako_intelligence.core.auth import COOKIE_NAME, hash_password
from mako_intelligence.db.models import (
    AuthSession,
    LocalCredential,
    Organization,
    OrganizationDirectCredential,
    OrganizationMembership,
    Project,
    ProjectDirectBinding,
    ProjectEvent,
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


def create_project_request(
    client: TestClient,
    organization_id: uuid.UUID,
    *,
    name: str = "  Новый проект  ",
    slug: str = "new-project",
    headers: dict[str, str] | None = None,
):
    return client.post(
        f"/organizations/{organization_id}/projects",
        json={"name": name, "slug": slug},
        headers={"Origin": ORIGIN} if headers is None else headers,
    )


def test_unauthenticated_project_create_is_denied(api) -> None:
    client, _db, ids, _pw = api
    response = create_project_request(client, ids["org"])
    assert response.status_code == 401


def test_org_owner_can_create_empty_project_and_read_it(api) -> None:
    client, db, ids, password = api
    assert sign_in(client, db.get(User, ids["owner"]).email, password).status_code == 200

    response = create_project_request(client, ids["org"])
    assert response.status_code == 201
    created = response.json()
    assert created["name"] == "Новый проект"
    assert created["slug"] == "new-project"
    assert created["status"] == "active"
    assert created["actions"] == ["edit", "manage_members", "view"]
    project_id = uuid.UUID(created["id"])
    assert db.get(Project, project_id).organization_id == ids["org"]
    assert client.get(
        f"/organizations/{ids['org']}/projects/{project_id}"
    ).status_code == 200
    listed = client.get(f"/organizations/{ids['org']}/projects").json()
    assert created["id"] in [p["id"] for p in listed]


def test_org_admin_can_create_project(api) -> None:
    client, db, ids, password = api
    membership = db.get(OrganizationMembership, (ids["org"], ids["member"]))
    membership.role = "admin"
    db.flush()
    assert sign_in(client, db.get(User, ids["member"]).email, password).status_code == 200
    response = create_project_request(client, ids["org"], slug="admin-project")
    assert response.status_code == 201


def test_regular_member_even_manager_cannot_create_project(api) -> None:
    client, db, ids, password = api
    membership = db.get(ProjectMembership, (ids["first"], ids["member"]))
    membership.role = "manager"
    db.flush()
    assert sign_in(client, db.get(User, ids["member"]).email, password).status_code == 200
    response = create_project_request(client, ids["org"])
    assert response.status_code == 403
    assert db.scalar(select(Project).where(Project.slug == "new-project")) is None


def test_nonmember_cannot_create_in_other_organization(api) -> None:
    client, db, ids, password = api
    assert sign_in(client, db.get(User, ids["stranger"]).email, password).status_code == 200
    assert create_project_request(client, ids["org"]).status_code == 404


def test_cross_org_creation_requires_membership_not_submitted_user_id(api) -> None:
    client, db, ids, password = api
    assert sign_in(client, db.get(User, ids["owner"]).email, password).status_code == 200
    response = client.post(
        f"/organizations/{ids['other_org']}/projects",
        json={"name": "Forbidden", "slug": "foreign-new", "user_id": str(ids["stranger"])},
        headers={"Origin": ORIGIN},
    )
    assert response.status_code == 404


def test_missing_or_untrusted_origin_prevents_project_creation(api) -> None:
    client, db, ids, password = api
    assert sign_in(client, db.get(User, ids["owner"]).email, password).status_code == 200
    for headers in ({}, {"Origin": "https://attacker.example"}):
        assert create_project_request(client, ids["org"], headers=headers).status_code == 403
    assert db.scalar(select(Project).where(Project.slug == "new-project")) is None


def test_project_slug_must_be_valid_and_duplicate_is_conflict(api) -> None:
    client, db, ids, password = api
    assert sign_in(client, db.get(User, ids["owner"]).email, password).status_code == 200

    for slug in ("xx", "UPPER", "bad slug", "кириллица", "-leading", "trailing-",
                 "x" * 81):
        assert create_project_request(client, ids["org"], slug=slug).status_code == 422
    assert create_project_request(client, ids["org"], name="   ").status_code == 422
    assert create_project_request(client, ids["org"], name="x" * 201).status_code == 422

    assert create_project_request(client, ids["org"], slug="first").status_code == 409
    assert create_project_request(client, ids["org"], slug="new-project").status_code == 201
    assert create_project_request(client, ids["org"], slug="new-project").status_code == 409


def test_same_slug_is_allowed_in_different_organizations(api) -> None:
    client, db, ids, password = api
    assert sign_in(client, db.get(User, ids["owner"]).email, password).status_code == 200
    first = create_project_request(client, ids["org"], slug="shared-code")
    assert first.status_code == 201
    assert sign_in(client, db.get(User, ids["stranger"]).email, password).status_code == 200
    second = create_project_request(client, ids["other_org"], slug="shared-code")
    assert second.status_code == 201
    assert first.json()["id"] != second.json()["id"]
    assert client.get(
        f"/organizations/{ids['org']}/projects/{first.json()['id']}"
    ).status_code == 404


def rename_request(
    client: TestClient,
    org: uuid.UUID,
    project: uuid.UUID,
    name: str = "  Новое название  ",
    headers: dict[str, str] | None = None,
):
    return client.patch(
        f"/organizations/{org}/projects/{project}",
        json={"name": name},
        headers={"Origin": ORIGIN} if headers is None else headers,
    )


def test_owner_can_rename_existing_project_without_changing_code_or_id(api) -> None:
    client, db, ids, password = api
    assert sign_in(client, db.get(User, ids["owner"]).email, password).status_code == 200
    response = rename_request(client, ids["org"], ids["first"])
    assert response.status_code == 200
    assert response.json()["name"] == "Новое название"
    assert response.json()["id"] == str(ids["first"])
    assert response.json()["slug"] == "first"
    assert db.get(Project, ids["first"]).name == "Новое название"
    assert client.get(f"/organizations/{ids['org']}/projects/{ids['first']}").json()[
        "name"
    ] == "Новое название"


def test_admin_can_rename_existing_active_project(api) -> None:
    client, db, ids, password = api
    membership = db.get(OrganizationMembership, (ids["org"], ids["member"]))
    membership.role = "admin"
    db.flush()
    assert sign_in(client, db.get(User, ids["member"]).email, password).status_code == 200
    assert rename_request(client, ids["org"], ids["second"], "Admin rename").status_code == 200


def test_project_manager_cannot_rename_identity_metadata(api) -> None:
    client, db, ids, password = api
    membership = db.get(ProjectMembership, (ids["first"], ids["member"]))
    membership.role = "manager"
    db.flush()
    assert sign_in(client, db.get(User, ids["member"]).email, password).status_code == 200
    assert rename_request(client, ids["org"], ids["first"]).status_code == 403
    assert db.get(Project, ids["first"]).name == "First"


def test_cross_org_rename_is_nondisclosing_not_found(api) -> None:
    client, db, ids, password = api
    assert sign_in(client, db.get(User, ids["owner"]).email, password).status_code == 200
    assert rename_request(client, ids["other_org"], ids["other_project"]).status_code == 404
    assert rename_request(client, ids["org"], ids["other_project"]).status_code == 404
    assert rename_request(client, ids["org"], uuid.uuid4()).status_code == 404


def test_unauthenticated_project_rename_is_denied(api) -> None:
    client, _db, ids, _password = api
    assert rename_request(client, ids["org"], ids["first"]).status_code == 401


def test_project_rename_requires_exact_origin(api) -> None:
    client, db, ids, password = api
    assert sign_in(client, db.get(User, ids["owner"]).email, password).status_code == 200
    for headers in ({}, {"Origin": "https://attacker.example"}):
        assert rename_request(
            client, ids["org"], ids["first"], headers=headers
        ).status_code == 403
    assert db.get(Project, ids["first"]).name == "First"


def test_archived_project_cannot_be_renamed_even_by_owner(api) -> None:
    client, db, ids, password = api
    assert sign_in(client, db.get(User, ids["owner"]).email, password).status_code == 200
    assert rename_request(client, ids["org"], ids["archived"]).status_code == 409
    assert db.get(Project, ids["archived"]).name == "Archived"


def test_project_rename_rejects_invalid_names(api) -> None:
    client, db, ids, password = api
    assert sign_in(client, db.get(User, ids["owner"]).email, password).status_code == 200
    for name in ("", "  ", "x" * 201):
        assert rename_request(client, ids["org"], ids["first"], name).status_code == 422
    assert db.get(Project, ids["first"]).name == "First"


def test_project_rename_preflight_allows_only_local_origin(api) -> None:
    client, _db, ids, _password = api
    url = f"/organizations/{ids['org']}/projects/{ids['first']}"
    allowed = client.options(url, headers={
        "Origin": ORIGIN,
        "Access-Control-Request-Method": "PATCH",
        "Access-Control-Request-Headers": "content-type",
    })
    assert allowed.status_code == 200
    assert allowed.headers.get("access-control-allow-origin") == ORIGIN
    assert "PATCH" in allowed.headers.get("access-control-allow-methods", "")
    denied = client.options(url, headers={
        "Origin": "https://attacker.example",
        "Access-Control-Request-Method": "PATCH",
    })
    assert denied.headers.get("access-control-allow-origin") is None


def change_status_request(
    client: TestClient,
    org: uuid.UUID,
    project: uuid.UUID,
    action: str,
    headers: dict[str, str] | None = None,
):
    return client.post(
        f"/organizations/{org}/projects/{project}/{action}",
        headers={"Origin": ORIGIN} if headers is None else headers,
    )


def test_owner_archive_restore_and_full_audit_history(api) -> None:
    client, db, ids, password = api
    assert sign_in(client, db.get(User, ids["owner"]).email, password).status_code == 200
    url = f"/organizations/{ids['org']}/projects/{ids['first']}"
    before_membership = db.get(ProjectMembership, (ids["first"], ids["member"]))
    assert before_membership is not None
    assert client.get(url + "/history").json() == []

    rename = rename_request(client, ids["org"], ids["first"], "  First renamed  ")
    assert rename.status_code == 200
    # Identical name must not create a redundant event.
    assert rename_request(client, ids["org"], ids["first"], "First renamed").status_code == 200

    archived = change_status_request(client, ids["org"], ids["first"], "archive")
    assert archived.status_code == 200
    assert archived.json()["status"] == "archived"
    assert archived.json()["actions"] == ["view"]
    assert client.get(url).json()["status"] == "archived"
    assert rename_request(client, ids["org"], ids["first"]).status_code == 409
    assert change_status_request(client, ids["org"], ids["first"], "archive").status_code == 409

    restored = change_status_request(client, ids["org"], ids["first"], "restore")
    assert restored.status_code == 200
    assert restored.json()["status"] == "active"
    assert "manage_members" in restored.json()["actions"]
    assert change_status_request(client, ids["org"], ids["first"], "restore").status_code == 409

    event_list = client.get(url + "/history")
    assert event_list.status_code == 200
    events = event_list.json()
    assert len(events) == 3
    by_action = {event["action"]: event for event in events}
    assert set(by_action) == {"rename", "archive", "restore"}
    assert by_action["rename"]["old_name"] == "First"
    assert by_action["rename"]["new_name"] == "First renamed"
    assert by_action["archive"]["old_status"] == "active"
    assert by_action["archive"]["new_status"] == "archived"
    assert by_action["restore"]["old_status"] == "archived"
    assert by_action["restore"]["new_status"] == "active"
    for event in events:
        assert event["actor"] == "Owner"
        assert event["actor_id"] == str(ids["owner"])
        assert event["created_at"]
    assert db.get(Project, ids["first"]).id == ids["first"]
    assert db.get(Project, ids["first"]).slug == "first"
    assert db.get(ProjectMembership, (ids["first"], ids["member"])) is not None


def test_admin_can_archive_and_restore_project(api) -> None:
    client, db, ids, password = api
    membership = db.get(OrganizationMembership, (ids["org"], ids["member"]))
    membership.role = "admin"
    db.flush()
    assert sign_in(client, db.get(User, ids["member"]).email, password).status_code == 200
    assert change_status_request(client, ids["org"], ids["second"], "archive").status_code == 200
    assert change_status_request(client, ids["org"], ids["second"], "restore").status_code == 200
    events = client.get(
        f"/organizations/{ids['org']}/projects/{ids['second']}/history"
    ).json()
    assert len(events) == 2 and all(event["actor"] == "Member" for event in events)


def test_member_even_manager_cannot_archive_restore_or_view_history(api) -> None:
    client, db, ids, password = api
    membership = db.get(ProjectMembership, (ids["first"], ids["member"]))
    membership.role = "manager"
    db.flush()
    assert sign_in(client, db.get(User, ids["member"]).email, password).status_code == 200
    for action in ("archive", "restore"):
        assert change_status_request(client, ids["org"], ids["first"], action).status_code == 403
    assert client.get(
        f"/organizations/{ids['org']}/projects/{ids['first']}/history"
    ).status_code == 403
    assert db.get(Project, ids["first"]).status == "active"


def test_outsider_and_wrong_org_ids_do_not_disclose_project_history(api) -> None:
    client, db, ids, password = api
    assert sign_in(client, db.get(User, ids["owner"]).email, password).status_code == 200
    for action in ("archive", "restore"):
        assert change_status_request(
            client, ids["other_org"], ids["other_project"], action
        ).status_code == 404
        assert change_status_request(
            client, ids["org"], ids["other_project"], action
        ).status_code == 404
    for org, project in (
        (ids["org"], ids["other_project"]), (ids["other_org"], ids["other_project"]),
        (ids["org"], uuid.uuid4()),
    ):
        assert client.get(
            f"/organizations/{org}/projects/{project}/history"
        ).status_code == 404


def test_unauthenticated_archive_restore_and_history_are_rejected(api) -> None:
    client, _db, ids, _pw = api
    for action in ("archive", "restore"):
        assert change_status_request(
            client, ids["org"], ids["first"], action
        ).status_code == 401
    assert client.get(
        f"/organizations/{ids['org']}/projects/{ids['first']}/history"
    ).status_code == 401


def test_archive_and_restore_require_exact_origin(api) -> None:
    client, db, ids, password = api
    assert sign_in(client, db.get(User, ids["owner"]).email, password).status_code == 200
    for action in ("archive", "restore"):
        for headers in ({}, {"Origin": "https://attacker.example"}):
            assert change_status_request(
                client, ids["org"], ids["first"], action, headers=headers
            ).status_code == 403
    assert db.get(Project, ids["first"]).status == "active"
    assert not db.scalar(select(ProjectEvent.id).limit(1))


def test_status_change_conflict_preserves_state_and_audit(api) -> None:
    client, db, ids, password = api
    assert sign_in(client, db.get(User, ids["owner"]).email, password).status_code == 200
    assert change_status_request(client, ids["org"], ids["archived"], "archive").status_code == 409
    assert change_status_request(client, ids["org"], ids["first"], "restore").status_code == 409
    assert db.get(Project, ids["first"]).status == "active"
    assert db.get(Project, ids["archived"]).status == "archived"
    assert not db.scalar(select(ProjectEvent.id).limit(1))


def test_database_trigger_prohibits_deletion_and_rewriting_audit_rows(api) -> None:
    client, db, ids, password = api
    assert sign_in(client, db.get(User, ids["owner"]).email, password).status_code == 200
    assert change_status_request(client, ids["org"], ids["first"], "archive").status_code == 200
    event = db.scalar(select(ProjectEvent).where(ProjectEvent.project_id == ids["first"]))
    assert event is not None

    savepoint = db.begin_nested()
    with pytest.raises(DBAPIError):
        db.execute(update(ProjectEvent).where(ProjectEvent.id == event.id).values(action="rename"))
    savepoint.rollback()
    db.expire_all()

    savepoint = db.begin_nested()
    with pytest.raises(DBAPIError):
        db.execute(delete(ProjectEvent).where(ProjectEvent.id == event.id))
    savepoint.rollback()
    assert db.scalar(select(ProjectEvent.action).where(ProjectEvent.id == event.id)) == "archive"


def test_audit_events_must_reference_project_in_same_organization(api) -> None:
    client, db, ids, password = api
    assert sign_in(client, db.get(User, ids["owner"]).email, password).status_code == 200
    savepoint = db.begin_nested()
    with pytest.raises(DBAPIError):
        db.add(ProjectEvent(
            organization_id=ids["other_org"],
            project_id=ids["first"],
            actor_user_id=ids["owner"],
            action="rename", old_name="A", new_name="B",
        ))
        db.flush()
    savepoint.rollback()
    assert not db.scalar(select(ProjectEvent.id).limit(1))


def binding_url(org: uuid.UUID, project: uuid.UUID) -> str:
    return f"/organizations/{org}/projects/{project}/direct-binding"


def put_binding(
    client: TestClient,
    org: uuid.UUID,
    project: uuid.UUID,
    login: str = "client-example",
    *,
    headers: dict[str, str] | None = None,
    extra: dict | None = None,
):
    payload = {"client_login": login}
    if extra is not None:
        payload.update(extra)
    return client.put(
        binding_url(org, project),
        json=payload,
        headers={"Origin": ORIGIN} if headers is None else headers,
    )


def remove_binding_request(
    client: TestClient,
    org: uuid.UUID,
    project: uuid.UUID,
    *,
    headers: dict[str, str] | None = None,
):
    return client.delete(
        binding_url(org, project),
        headers={"Origin": ORIGIN} if headers is None else headers,
    )


def test_direct_binding_requires_authenticated_user(api) -> None:
    client, _db, ids, _password = api
    url = binding_url(ids["org"], ids["first"])
    assert client.get(url).status_code == 401
    assert put_binding(client, ids["org"], ids["first"]).status_code == 401
    assert remove_binding_request(client, ids["org"], ids["first"]).status_code == 401


def test_owner_can_configure_read_change_and_unlink_without_storing_token(api) -> None:
    client, db, ids, password = api
    assert sign_in(client, db.get(User, ids["owner"]).email, password).status_code == 200
    url = binding_url(ids["org"], ids["first"])
    assert client.get(url).json() == {
        "provider": "yandex_direct", "client_login": None,
        "status": "not_configured", "credential_available": False,
        "last_verified_at": None, "campaign_count": None,
    }
    response = put_binding(client, ids["org"], ids["first"])
    assert response.status_code == 200
    assert response.json() == {
        "provider": "yandex_direct", "client_login": "client-example",
        "status": "configured_unverified", "credential_available": False,
        "last_verified_at": None, "campaign_count": None,
    }
    record = db.get(ProjectDirectBinding, ids["first"])
    assert record is not None
    assert record.organization_id == ids["org"]
    assert record.status == "configured_unverified"

    # No duplicate audit event when saving the exact same value.
    assert put_binding(client, ids["org"], ids["first"]).status_code == 200
    assert put_binding(client, ids["org"], ids["first"], "client-other").status_code == 200

    history = client.get(
        f"/organizations/{ids['org']}/projects/{ids['first']}/history"
    ).json()
    assert len(history) == 2
    assert all(event["action"] == "direct_bind" for event in history)
    first_event = next(
        event for event in history if event["old_client_login"] is None
    )
    assert first_event["new_client_login"] == "client-example"
    assert all(event["actor_id"] == str(ids["owner"]) for event in history)

    removed = remove_binding_request(client, ids["org"], ids["first"])
    assert removed.status_code == 204
    assert db.get(ProjectDirectBinding, ids["first"]) is None
    assert client.get(url).json()["status"] == "not_configured"
    assert remove_binding_request(client, ids["org"], ids["first"]).status_code == 404

    history = client.get(
        f"/organizations/{ids['org']}/projects/{ids['first']}/history"
    ).json()
    assert len(history) == 3
    assert any(
        item["action"] == "direct_unbind"
        and item["old_client_login"] == "client-other"
        and item["new_client_login"] is None
        for item in history
    )


def test_org_admin_can_bind_only_active_project(api) -> None:
    client, db, ids, password = api
    membership = db.get(OrganizationMembership, (ids["org"], ids["member"]))
    membership.role = "admin"
    db.flush()
    assert sign_in(client, db.get(User, ids["member"]).email, password).status_code == 200
    assert put_binding(client, ids["org"], ids["second"], "permitted").status_code == 200


def test_regular_member_even_manager_cannot_read_or_modify_connection(api) -> None:
    client, db, ids, password = api
    membership = db.get(ProjectMembership, (ids["first"], ids["member"]))
    membership.role = "manager"
    db.flush()
    assert sign_in(client, db.get(User, ids["member"]).email, password).status_code == 200
    url = binding_url(ids["org"], ids["first"])
    assert client.get(url).status_code == 403
    assert put_binding(client, ids["org"], ids["first"]).status_code == 403
    assert remove_binding_request(client, ids["org"], ids["first"]).status_code == 403


def test_direct_binding_never_discloses_cross_org_projects(api) -> None:
    client, db, ids, password = api
    assert sign_in(client, db.get(User, ids["owner"]).email, password).status_code == 200
    for org, project in (
        (ids["other_org"], ids["other_project"]),
        (ids["org"], ids["other_project"]),
        (ids["org"], uuid.uuid4()),
    ):
        url = binding_url(org, project)
        assert client.get(url).status_code == 404
        assert put_binding(client, org, project).status_code == 404
        assert remove_binding_request(client, org, project).status_code == 404

    assert db.scalar(select(ProjectDirectBinding.project_id).limit(1)) is None


def test_archived_projects_are_read_only_for_direct_binding(api) -> None:
    client, db, ids, password = api
    assert sign_in(client, db.get(User, ids["owner"]).email, password).status_code == 200
    assert client.get(binding_url(ids["org"], ids["archived"])).status_code == 200
    assert put_binding(client, ids["org"], ids["archived"]).status_code == 409
    assert remove_binding_request(client, ids["org"], ids["archived"]).status_code == 409


def test_direct_binding_mutations_require_same_frontend_origin(api) -> None:
    client, db, ids, password = api
    assert sign_in(client, db.get(User, ids["owner"]).email, password).status_code == 200
    for headers in ({}, {"Origin": "https://attacker.example"}):
        assert put_binding(
            client, ids["org"], ids["first"], headers=headers
        ).status_code == 403
    assert put_binding(client, ids["org"], ids["first"]).status_code == 200
    for headers in ({}, {"Origin": "https://attacker.example"}):
        assert remove_binding_request(
            client, ids["org"], ids["first"], headers=headers
        ).status_code == 403
    assert db.get(ProjectDirectBinding, ids["first"]) is not None


@pytest.mark.parametrize(
    "login", ["", "bad login", "bad\nlogin", "../thing", "кириллица", "-bad", "x" * 256]
)
def test_direct_login_validation(login: str, api) -> None:
    client, db, ids, password = api
    assert sign_in(client, db.get(User, ids["owner"]).email, password).status_code == 200
    assert put_binding(client, ids["org"], ids["first"], login).status_code == 422
    assert db.get(ProjectDirectBinding, ids["first"]) is None


def test_direct_binding_rejects_unexpected_credential_fields(api) -> None:
    client, db, ids, password = api
    assert sign_in(client, db.get(User, ids["owner"]).email, password).status_code == 200
    assert put_binding(
        client, ids["org"], ids["first"],
        extra={"oauth_token": "NOT-A-REAL-SECRET"},
    ).status_code == 422
    assert db.get(ProjectDirectBinding, ids["first"]) is None


def test_binding_has_database_tenant_foreign_key(api) -> None:
    _client, db, ids, _password = api
    savepoint = db.begin_nested()
    with pytest.raises(DBAPIError):
        db.add(ProjectDirectBinding(
            organization_id=ids["other_org"],
            project_id=ids["first"],
            client_login="bad-tenant",
        ))
        db.flush()
    savepoint.rollback()
    assert not db.scalar(select(ProjectDirectBinding.project_id).limit(1))


def test_direct_binding_preflight_allows_only_trusted_origin(api) -> None:
    client, _db, ids, _password = api
    url = binding_url(ids["org"], ids["first"])
    for method in ("PUT", "DELETE"):
        response = client.options(url, headers={
            "Origin": ORIGIN, "Access-Control-Request-Method": method,
            "Access-Control-Request-Headers": "content-type",
        })
        assert response.status_code == 200
        assert response.headers.get("access-control-allow-origin") == ORIGIN
        assert method in response.headers.get("access-control-allow-methods", "")
    response = client.options(url, headers={
        "Origin": "https://attacker.example", "Access-Control-Request-Method": "PUT",
    })
    assert response.headers.get("access-control-allow-origin") is None


def test_binding_is_organization_scoped_even_with_same_login(api) -> None:
    client, db, ids, password = api
    assert sign_in(client, db.get(User, ids["owner"]).email, password).status_code == 200
    assert put_binding(client, ids["org"], ids["first"], "shared-login").status_code == 200
    assert sign_in(client, db.get(User, ids["stranger"]).email, password).status_code == 200
    assert put_binding(
        client, ids["other_org"], ids["other_project"], "shared-login"
    ).status_code == 200
    assert client.get(binding_url(ids["org"], ids["first"])).status_code == 404
    other = client.get(binding_url(ids["other_org"], ids["other_project"])).json()
    assert other["client_login"] == "shared-login"


def verify_path(org: uuid.UUID, project: uuid.UUID) -> str:
    return f"/organizations/{org}/projects/{project}/direct-verify"


def set_test_agency_token(db: Session, org: uuid.UUID, token: str = "FAKE-NOT-REAL"):
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM

    from mako_intelligence.integrations.direct_vault import DirectVault

    key = AESGCM.generate_key(bit_length=256)
    vault = DirectVault(key)
    db.add(OrganizationDirectCredential(
        organization_id=org, encrypted_token=vault.seal(token, org), revision=1,
    ))
    db.flush()
    return key


def stub_direct_verify(monkeypatch, key, *, agency_login="client-example",
                       campaigns=3, error=None):
    from mako_intelligence.api.routes import direct_verification
    from mako_intelligence.integrations.yandex_direct import DirectReadError

    calls: list[str] = []

    class FakeDirect:
        def __init__(self, token):
            assert token == "FAKE-NOT-REAL"

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return None

        def get_agency_clients(self):
            calls.append("agency")
            if error is not None:
                raise DirectReadError("redacted provider error", error_code=error)
            return [{"Login": agency_login}]

        def get_campaigns(self, *, client_login):
            calls.append("campaigns:" + client_login)
            return [{"Id": i, "Name": "Synthetic"} for i in range(campaigns)]

    monkeypatch.setattr(direct_verification, "DirectReadClient", FakeDirect)
    monkeypatch.setattr(direct_verification, "load_vault_key", lambda: key)
    return calls


def test_owner_verifies_bound_advertiser_and_sees_count_not_token(api, monkeypatch) -> None:
    client, db, ids, password = api
    assert sign_in(client, db.get(User, ids["owner"]).email, password).status_code == 200
    assert put_binding(client, ids["org"], ids["first"]).status_code == 200
    key = set_test_agency_token(db, ids["org"])
    calls = stub_direct_verify(monkeypatch, key)

    response = client.post(verify_path(ids["org"], ids["first"]), headers={"Origin": ORIGIN})
    assert response.status_code == 200
    value = response.json()
    assert value["status"] == "verified_at_time"
    assert value["campaign_count"] == 3
    assert value["last_verified_at"] is not None
    assert value["credential_available"] is True
    assert "FAKE-NOT-REAL" not in response.text
    assert calls == ["agency", "campaigns:client-example"]

    stored = db.get(ProjectDirectBinding, ids["first"])
    assert stored.verified_token_revision == 1
    assert stored.verified_campaign_count == 3
    assert client.get(binding_url(ids["org"], ids["first"])).json()["status"] == (
        "verified_at_time"
    )


def test_repeat_direct_verify_uses_one_minute_cooldown(api, monkeypatch) -> None:
    client, db, ids, password = api
    sign_in(client, db.get(User, ids["owner"]).email, password)
    put_binding(client, ids["org"], ids["first"])
    key = set_test_agency_token(db, ids["org"])
    calls = stub_direct_verify(monkeypatch, key)
    url = verify_path(ids["org"], ids["first"])
    assert client.post(url, headers={"Origin": ORIGIN}).status_code == 200
    assert client.post(url, headers={"Origin": ORIGIN}).status_code == 200
    assert calls == ["agency", "campaigns:client-example"]


def test_changing_direct_login_invalidates_last_verification(api, monkeypatch) -> None:
    client, db, ids, password = api
    sign_in(client, db.get(User, ids["owner"]).email, password)
    put_binding(client, ids["org"], ids["first"])
    key = set_test_agency_token(db, ids["org"])
    stub_direct_verify(monkeypatch, key)
    assert client.post(
        verify_path(ids["org"], ids["first"]), headers={"Origin": ORIGIN}
    ).status_code == 200
    assert put_binding(client, ids["org"], ids["first"], "new-login").status_code == 200
    value = client.get(binding_url(ids["org"], ids["first"])).json()
    assert value["status"] == "configured_unverified"
    assert value["campaign_count"] is None
    assert value["last_verified_at"] is None


def test_replacing_agency_credential_requires_new_verification(api, monkeypatch) -> None:
    client, db, ids, password = api
    sign_in(client, db.get(User, ids["owner"]).email, password)
    put_binding(client, ids["org"], ids["first"])
    key = set_test_agency_token(db, ids["org"])
    stub_direct_verify(monkeypatch, key)
    client.post(verify_path(ids["org"], ids["first"]), headers={"Origin": ORIGIN})
    credential = db.get(OrganizationDirectCredential, ids["org"])
    credential.revision += 1
    db.commit()
    value = client.get(binding_url(ids["org"], ids["first"])).json()
    assert value["status"] == "configured_unverified"
    assert value["last_verified_at"] is None


def test_verify_requires_credential_and_binding(api) -> None:
    client, db, ids, password = api
    sign_in(client, db.get(User, ids["owner"]).email, password)
    url = verify_path(ids["org"], ids["first"])
    assert client.post(url, headers={"Origin": ORIGIN}).status_code == 409
    put_binding(client, ids["org"], ids["first"])
    assert client.post(url, headers={"Origin": ORIGIN}).status_code == 409


def test_verify_denies_member_outsider_and_unauthenticated(api, monkeypatch) -> None:
    client, db, ids, password = api
    url = verify_path(ids["org"], ids["first"])
    assert client.post(url, headers={"Origin": ORIGIN}).status_code == 401
    sign_in(client, db.get(User, ids["member"]).email, password)
    assert client.post(url, headers={"Origin": ORIGIN}).status_code == 403
    sign_in(client, db.get(User, ids["stranger"]).email, password)
    assert client.post(url, headers={"Origin": ORIGIN}).status_code == 404


def test_verify_refuses_archived_and_wrong_tenant_projects(api) -> None:
    client, db, ids, password = api
    sign_in(client, db.get(User, ids["owner"]).email, password)
    assert client.post(
        verify_path(ids["org"], ids["archived"]), headers={"Origin": ORIGIN}
    ).status_code == 409
    assert client.post(
        verify_path(ids["other_org"], ids["other_project"]), headers={"Origin": ORIGIN}
    ).status_code == 404
    assert client.post(
        verify_path(ids["org"], ids["other_project"]), headers={"Origin": ORIGIN}
    ).status_code == 404


def test_verify_requires_origin_before_network(api, monkeypatch) -> None:
    client, db, ids, password = api
    sign_in(client, db.get(User, ids["owner"]).email, password)
    put_binding(client, ids["org"], ids["first"])
    key = set_test_agency_token(db, ids["org"])
    calls = stub_direct_verify(monkeypatch, key)
    for headers in ({}, {"Origin": "https://attacker.example"}):
        assert client.post(verify_path(ids["org"], ids["first"]), headers=headers).status_code == 403
    assert calls == []


def test_direct_verify_denies_unlisted_agency_client(api, monkeypatch) -> None:
    client, db, ids, password = api
    sign_in(client, db.get(User, ids["owner"]).email, password)
    put_binding(client, ids["org"], ids["first"])
    key = set_test_agency_token(db, ids["org"])
    calls = stub_direct_verify(monkeypatch, key, agency_login="another-advertiser")
    response = client.post(
        verify_path(ids["org"], ids["first"]), headers={"Origin": ORIGIN}
    )
    assert response.status_code == 403
    assert calls == ["agency"]
    assert db.get(ProjectDirectBinding, ids["first"]).verified_at is None


def test_direct_verify_sanitizes_upstream_error_and_does_not_save(api, monkeypatch) -> None:
    client, db, ids, password = api
    sign_in(client, db.get(User, ids["owner"]).email, password)
    put_binding(client, ids["org"], ids["first"])
    key = set_test_agency_token(db, ids["org"])
    stub_direct_verify(monkeypatch, key, error=58)
    response = client.post(
        verify_path(ids["org"], ids["first"]), headers={"Origin": ORIGIN}
    )
    assert response.status_code == 502
    assert "58" in response.text
    assert "FAKE-NOT-REAL" not in response.text
    assert db.get(ProjectDirectBinding, ids["first"]).verified_at is None


def test_direct_verify_key_unavailable_returns_503_without_leaking(api, monkeypatch) -> None:
    from mako_intelligence.api.routes import direct_verification
    from mako_intelligence.integrations.direct_vault import DirectVaultError

    client, db, ids, password = api
    sign_in(client, db.get(User, ids["owner"]).email, password)
    put_binding(client, ids["org"], ids["first"])
    set_test_agency_token(db, ids["org"])

    def no_key():
        raise DirectVaultError("key unavailable")

    monkeypatch.setattr(direct_verification, "load_vault_key", no_key)
    response = client.post(
        verify_path(ids["org"], ids["first"]), headers={"Origin": ORIGIN}
    )
    assert response.status_code == 503
    assert "FAKE-NOT-REAL" not in response.text


def preview_url(org: uuid.UUID, project: uuid.UUID) -> str:
    return f"/organizations/{org}/projects/{project}/direct-campaign-preview"


def prepare_verified_preview(api, monkeypatch):
    """Set up a synthetic preverified advertiser without contacting Yandex."""
    client, db, ids, password = api
    assert sign_in(client, db.get(User, ids["owner"]).email, password).status_code == 200
    assert put_binding(client, ids["org"], ids["first"]).status_code == 200
    key = set_test_agency_token(db, ids["org"])
    stub_direct_verify(monkeypatch, key)
    result = client.post(verify_path(ids["org"], ids["first"]), headers={"Origin": ORIGIN})
    assert result.status_code == 200
    return client, db, ids, key


def stub_campaign_preview(monkeypatch, key, *, rows=None, error=None, on_fetch=None):
    from mako_intelligence.api.routes import direct_campaigns
    from mako_intelligence.integrations.yandex_direct import DirectReadError

    if rows is None:
        rows = [
            {"Id": 39, "Name": "Z-test"},
            {"Id": 11, "Name": "Alpha"},
            {"Id": 27, "Name": "Бета"},
        ]
    calls = []

    class FakeDirect:
        def __init__(self, token):
            assert token == "FAKE-NOT-REAL"
        def __enter__(self):
            return self
        def __exit__(self, *_args):
            return None
        def get_campaigns(self, *, client_login):
            calls.append(client_login)
            if on_fetch is not None:
                on_fetch()
            if error is not None:
                raise DirectReadError("never print secret", error_code=error)
            return rows

    monkeypatch.setattr(direct_campaigns, "DirectReadClient", FakeDirect)
    monkeypatch.setattr(direct_campaigns, "load_vault_key", lambda: key)
    return calls


def test_preview_reads_only_selected_advertiser_and_returns_names_ids(api, monkeypatch) -> None:
    client, db, ids, key = prepare_verified_preview(api, monkeypatch)
    calls = stub_campaign_preview(monkeypatch, key)
    response = client.post(preview_url(ids["org"], ids["first"]), headers={"Origin": ORIGIN})
    assert response.status_code == 200
    result = response.json()
    assert result["count"] == 3
    assert [item["id"] for item in result["campaigns"]] == [11, 39, 27]
    assert result["campaigns"][0]["name"] == "Alpha"
    assert result["fetched_at"]
    assert response.headers.get("cache-control") == "no-store"
    assert calls == ["client-example"]
    assert "FAKE-NOT-REAL" not in response.text
    assert "agency" not in response.text
    # The inventory is ephemeral and only the previous count remains in DB.
    stored = db.get(ProjectDirectBinding, ids["first"])
    assert stored.verified_campaign_count == 3


def test_preview_requires_current_verified_binding_and_credential(api, monkeypatch) -> None:
    client, db, ids, password = api
    assert sign_in(client, db.get(User, ids["owner"]).email, password).status_code == 200
    path = preview_url(ids["org"], ids["first"])
    assert client.post(path, headers={"Origin": ORIGIN}).status_code == 409
    put_binding(client, ids["org"], ids["first"])
    assert client.post(path, headers={"Origin": ORIGIN}).status_code == 409
    key = set_test_agency_token(db, ids["org"])
    calls = stub_campaign_preview(monkeypatch, key)
    assert client.post(path, headers={"Origin": ORIGIN}).status_code == 409
    assert calls == []


def test_preview_denies_member_stranger_cross_org_archived_or_no_session(api) -> None:
    client, db, ids, password = api
    path = preview_url(ids["org"], ids["first"])
    assert client.post(path, headers={"Origin": ORIGIN}).status_code == 401
    sign_in(client, db.get(User, ids["member"]).email, password)
    assert client.post(path, headers={"Origin": ORIGIN}).status_code == 403
    sign_in(client, db.get(User, ids["stranger"]).email, password)
    assert client.post(path, headers={"Origin": ORIGIN}).status_code == 404
    sign_in(client, db.get(User, ids["owner"]).email, password)
    assert client.post(
        preview_url(ids["other_org"], ids["other_project"]), headers={"Origin": ORIGIN}
    ).status_code == 404
    assert client.post(
        preview_url(ids["org"], ids["other_project"]), headers={"Origin": ORIGIN}
    ).status_code == 404
    assert client.post(
        preview_url(ids["org"], ids["archived"]), headers={"Origin": ORIGIN}
    ).status_code == 409


def test_preview_denies_missing_or_foreign_origin_before_api_call(api, monkeypatch) -> None:
    client, db, ids, key = prepare_verified_preview(api, monkeypatch)
    calls = stub_campaign_preview(monkeypatch, key)
    for headers in ({}, {"Origin": "https://attacker.example"}):
        assert client.post(preview_url(ids["org"], ids["first"]), headers=headers).status_code == 403
    assert calls == []


def test_preview_denies_stale_verification_before_network(api, monkeypatch) -> None:
    from datetime import timedelta

    client, db, ids, key = prepare_verified_preview(api, monkeypatch)
    calls = stub_campaign_preview(monkeypatch, key)
    record = db.get(ProjectDirectBinding, ids["first"])
    record.verified_at -= timedelta(hours=25)
    db.commit()
    assert client.post(
        preview_url(ids["org"], ids["first"]), headers={"Origin": ORIGIN}
    ).status_code == 409
    assert calls == []


def test_preview_rejects_invalid_provider_campaign_shapes(api, monkeypatch) -> None:
    client, db, ids, key = prepare_verified_preview(api, monkeypatch)
    for item in (
        {"Id": True, "Name": "Boolean id"},
        {"Id": 0, "Name": "Zero id"},
        {"Id": 1, "Name": ""},
        {"Id": 1, "Name": "x" * 256},
        {"Id": 1, "Name": None},
    ):
        stub_campaign_preview(monkeypatch, key, rows=[item])
        result = client.post(preview_url(ids["org"], ids["first"]), headers={"Origin": ORIGIN})
        assert result.status_code == 502
        assert "FAKE-NOT-REAL" not in result.text


def test_preview_refuses_unbounded_number_of_campaigns(api, monkeypatch) -> None:
    client, db, ids, key = prepare_verified_preview(api, monkeypatch)
    rows = [{"Id": index + 1, "Name": "Fake"} for index in range(1001)]
    stub_campaign_preview(monkeypatch, key, rows=rows)
    result = client.post(preview_url(ids["org"], ids["first"]), headers={"Origin": ORIGIN})
    assert result.status_code == 502
    assert "limit" in result.text


def test_preview_returns_redacted_provider_failures(api, monkeypatch) -> None:
    client, db, ids, key = prepare_verified_preview(api, monkeypatch)
    stub_campaign_preview(monkeypatch, key, error=58)
    result = client.post(preview_url(ids["org"], ids["first"]), headers={"Origin": ORIGIN})
    assert result.status_code == 502
    assert "58" in result.text
    assert "never print secret" not in result.text
    assert "FAKE-NOT-REAL" not in result.text


def test_preview_cannot_return_campaigns_if_binding_changed_during_fetch(api, monkeypatch) -> None:
    client, db, ids, key = prepare_verified_preview(api, monkeypatch)
    def switch_login() -> None:
        binding = db.get(ProjectDirectBinding, ids["first"])
        binding.client_login = "different-client"
        binding.verified_at = None
        binding.verified_token_revision = None
        db.commit()
    calls = stub_campaign_preview(monkeypatch, key, on_fetch=switch_login)
    result = client.post(preview_url(ids["org"], ids["first"]), headers={"Origin": ORIGIN})
    assert result.status_code == 409
    assert calls == ["client-example"]
    assert "Alpha" not in result.text


def test_preview_denies_key_error_without_credential_or_campaign_leak(api, monkeypatch) -> None:
    from mako_intelligence.api.routes import direct_campaigns
    from mako_intelligence.integrations.direct_vault import DirectVaultError

    client, db, ids, key = prepare_verified_preview(api, monkeypatch)
    def missing_key():
        raise DirectVaultError("No key")
    monkeypatch.setattr(direct_campaigns, "load_vault_key", missing_key)
    result = client.post(preview_url(ids["org"], ids["first"]), headers={"Origin": ORIGIN})
    assert result.status_code == 503
    assert "FAKE-NOT-REAL" not in result.text
