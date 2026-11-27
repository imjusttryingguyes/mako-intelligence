"""Integration tests run only against a disposable MAKO_TEST_DATABASE_URL.

CI provides PostgreSQL and applies Alembic migrations before these tests.
No customer data is used; all sample rows are rolled back.
"""
import os
import uuid

import pytest
from sqlalchemy import create_engine, inspect, text
from sqlalchemy.exc import IntegrityError

TEST_URL = os.getenv("MAKO_TEST_DATABASE_URL")
pytestmark = pytest.mark.skipif(not TEST_URL, reason="No isolated test database configured")


def test_initial_migration_created_expected_tables() -> None:
    engine = create_engine(TEST_URL)
    try:
        names = set(inspect(engine).get_table_names())
        assert {
            "alembic_version", "organizations", "users", "organization_memberships",
            "auth_sessions", "local_credentials", "project_events",
            "projects", "project_memberships",
        } <= names
        with engine.connect() as connection:
            assert connection.execute(
                text("SELECT version_num FROM alembic_version")
            ).scalar_one() == "0003_project_events"
    finally:
        engine.dispose()


def test_cross_tenant_project_membership_is_rejected() -> None:
    engine = create_engine(TEST_URL)
    try:
        with engine.connect() as connection:
            transaction = connection.begin()
            try:
                org_a, org_b, user_id, project_id = [uuid.uuid4() for _ in range(4)]
                connection.execute(
                    text("INSERT INTO organizations(id, slug, name) VALUES "
                         "(:a, :slug_a, 'Agency'), (:b, :slug_b, 'Other')"),
                    {"a": org_a, "b": org_b,
                     "slug_a": f"agency-{org_a.hex[:12]}",
                     "slug_b": f"other-{org_b.hex[:12]}"},
                )
                connection.execute(
                    text("INSERT INTO users(id, email, display_name) "
                         "VALUES (:id, :email, 'Example User')"),
                    {"id": user_id, "email": f"test-{user_id.hex}@example.invalid"},
                )
                connection.execute(
                    text("INSERT INTO organization_memberships(organization_id, user_id, role) "
                         "VALUES (:org, :user, 'member')"),
                    {"org": org_a, "user": user_id},
                )
                connection.execute(
                    text("INSERT INTO projects(id, organization_id, slug, name) "
                         "VALUES (:id, :org, 'test-project', 'Test Project')"),
                    {"id": project_id, "org": org_b},
                )
                savepoint = connection.begin_nested()
                with pytest.raises(IntegrityError):
                    connection.execute(
                        text("INSERT INTO project_memberships("
                             "project_id, user_id, organization_id, role) "
                             "VALUES (:project, :user, :org, 'viewer')"),
                        {"project": project_id, "user": user_id, "org": org_b},
                    )
                savepoint.rollback()
            finally:
                transaction.rollback()
    finally:
        engine.dispose()


def test_email_uniqueness_ignores_case() -> None:
    engine = create_engine(TEST_URL)
    try:
        with engine.connect() as connection:
            transaction = connection.begin()
            try:
                email = f"tester-{uuid.uuid4().hex}@example.invalid"
                connection.execute(
                    text("INSERT INTO users(email, display_name) "
                         "VALUES (:email, 'Tester')"),
                    {"email": email},
                )
                savepoint = connection.begin_nested()
                with pytest.raises(IntegrityError):
                    connection.execute(
                        text("INSERT INTO users(email, display_name) "
                             "VALUES (:email, 'Duplicate')"),
                        {"email": email.upper()},
                    )
                savepoint.rollback()
            finally:
                transaction.rollback()
    finally:
        engine.dispose()
