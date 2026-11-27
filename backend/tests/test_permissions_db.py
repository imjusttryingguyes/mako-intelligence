"""Tenant-scoped integration tests, with synthetic rows and rollback only.

MAKO_TEST_DATABASE_URL must point to a disposable database (checked below).
"""
import os
import uuid

import pytest
from sqlalchemy import create_engine
from sqlalchemy.engine import make_url
from sqlalchemy.orm import Session

from mako_intelligence.core.permissions import (
    ProjectAction,
    project_permissions,
    visible_projects,
)
from mako_intelligence.db.models import (
    Organization,
    OrganizationMembership,
    Project,
    ProjectMembership,
    User,
)

TEST_URL = os.getenv("MAKO_TEST_DATABASE_URL")

pytestmark = pytest.mark.skipif(not TEST_URL, reason="No disposable test DB configured")


@pytest.fixture()
def dataset():
    assert TEST_URL is not None
    database_name = make_url(TEST_URL).database or ""
    if "test" not in database_name.lower():
        pytest.fail("MAKO_TEST_DATABASE_URL must point to an explicitly named test database")

    engine = create_engine(TEST_URL)
    connection = engine.connect()
    outer_transaction = connection.begin()
    session = Session(bind=connection, join_transaction_mode="create_savepoint")
    ids = {name: uuid.uuid4() for name in (
        "org_a", "org_b", "owner", "admin", "editor", "viewer", "external",
        "p1", "p2", "archived", "foreign_project",
    )}
    try:
        session.add_all([
            Organization(id=ids["org_a"], slug=f"org-a-{ids['org_a'].hex[:10]}", name="Agency"),
            Organization(id=ids["org_b"], slug=f"org-b-{ids['org_b'].hex[:10]}", name="Other"),
        ])
        session.add_all([
            User(
                id=ids[key], email=f"{key}-{ids[key].hex}@example.invalid",
                display_name=f"Test {key}",
            )
            for key in ("owner", "admin", "editor", "viewer", "external")
        ])
        session.flush()

        session.add_all([
            OrganizationMembership(
                organization_id=ids["org_a"], user_id=ids[role], role=org_role
            )
            for role, org_role in (
                ("owner", "owner"), ("admin", "admin"),
                ("editor", "member"), ("viewer", "member"),
            )
        ])
        session.add(OrganizationMembership(
            organization_id=ids["org_b"], user_id=ids["external"], role="owner",
        ))
        session.add_all([
            Project(
                id=ids[key], organization_id=ids[organization],
                slug=key.replace("_", "-"), name=key,
                status="archived" if key == "archived" else "active",
            )
            for key, organization in (
                ("p1", "org_a"), ("p2", "org_a"),
                ("archived", "org_a"), ("foreign_project", "org_b"),
            )
        ])
        session.flush()

        session.add_all([
            ProjectMembership(
                project_id=ids["p1"], user_id=ids["editor"],
                organization_id=ids["org_a"], role="editor",
            ),
            ProjectMembership(
                project_id=ids["p1"], user_id=ids["viewer"],
                organization_id=ids["org_a"], role="viewer",
            ),
            ProjectMembership(
                project_id=ids["archived"], user_id=ids["viewer"],
                organization_id=ids["org_a"], role="manager",
            ),
        ])
        session.flush()
        yield session, ids
    finally:
        session.close()
        outer_transaction.rollback()
        connection.close()
        engine.dispose()


@pytest.mark.parametrize("role", ["owner", "admin"])
def test_org_owner_and_admin_can_manage_own_projects(dataset, role: str) -> None:
    session, ids = dataset
    actions = project_permissions(
        session, user_id=ids[role], organization_id=ids["org_a"], project_id=ids["p2"],
    )
    assert ProjectAction.MANAGE_MEMBERS in actions
    assert not project_permissions(
        session, user_id=ids[role], organization_id=ids["org_b"],
        project_id=ids["foreign_project"],
    )


def test_explicit_member_access_is_project_scoped(dataset) -> None:
    session, ids = dataset
    actions = project_permissions(
        session, user_id=ids["editor"], organization_id=ids["org_a"],
        project_id=ids["p1"],
    )
    assert actions == {ProjectAction.VIEW, ProjectAction.EDIT}
    assert not project_permissions(
        session, user_id=ids["editor"], organization_id=ids["org_a"], project_id=ids["p2"],
    )


def test_unknown_and_wrong_organization_ids_do_not_disclose_projects(dataset) -> None:
    session, ids = dataset
    assert not project_permissions(
        session, user_id=ids["external"], organization_id=ids["org_a"], project_id=ids["p1"],
    )
    assert not project_permissions(
        session, user_id=ids["editor"], organization_id=ids["org_b"], project_id=ids["p1"],
    )
    assert not project_permissions(
        session, user_id=ids["owner"], organization_id=ids["org_a"],
        project_id=uuid.uuid4(),
    )


def test_archived_projects_are_view_only(dataset) -> None:
    session, ids = dataset
    for role in ("owner", "admin", "viewer"):
        assert project_permissions(
            session, user_id=ids[role], organization_id=ids["org_a"],
            project_id=ids["archived"],
        ) == {ProjectAction.VIEW}


def test_project_listing_only_contains_authorized_projects(dataset) -> None:
    session, ids = dataset

    owner_projects = visible_projects(
        session, user_id=ids["owner"], organization_id=ids["org_a"],
    )
    assert {project.id for project in owner_projects} == {
        ids["p1"], ids["p2"], ids["archived"],
    }

    editor_projects = visible_projects(
        session, user_id=ids["editor"], organization_id=ids["org_a"],
    )
    assert [project.id for project in editor_projects] == [ids["p1"]]
    assert editor_projects[0].actions == {ProjectAction.VIEW, ProjectAction.EDIT}

    viewer_projects = visible_projects(
        session, user_id=ids["viewer"], organization_id=ids["org_a"],
    )
    assert {project.id for project in viewer_projects} == {ids["p1"], ids["archived"]}

    assert not visible_projects(
        session, user_id=ids["external"], organization_id=ids["org_a"],
    )
    assert not visible_projects(
        session, user_id=ids["owner"], organization_id=ids["org_b"],
    )
    assert [p.id for p in visible_projects(
        session, user_id=ids["external"], organization_id=ids["org_b"],
    )] == [ids["foreign_project"]]
