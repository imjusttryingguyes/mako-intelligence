"""Pure authorization matrix: always runs, even without PostgreSQL."""
import pytest

from mako_intelligence.core.permissions import ProjectAction as Action
from mako_intelligence.core.permissions import resolve_project_actions


@pytest.mark.parametrize("role", ["owner", "admin"])
def test_org_lead_inherits_all_active_project_actions(role: str) -> None:
    assert resolve_project_actions(role, None, "active") == {
        Action.VIEW, Action.EDIT, Action.MANAGE_MEMBERS,
    }


@pytest.mark.parametrize(
    ("role", "expected"),
    [
        ("manager", {Action.VIEW, Action.EDIT, Action.MANAGE_MEMBERS}),
        ("editor", {Action.VIEW, Action.EDIT}),
        ("viewer", {Action.VIEW}),
    ],
)
def test_explicit_project_memberships(role: str, expected: set[Action]) -> None:
    assert resolve_project_actions("member", role, "active") == expected


@pytest.mark.parametrize(
    ("organization_role", "project_role", "status"),
    [
        (None, "manager", "active"),
        ("random", "manager", "active"),
        ("member", None, "active"),
        ("member", "not-a-role", "active"),
        ("owner", None, "unknown"),
        ("admin", "manager", "deleted"),
    ],
)
def test_unrecognized_or_missing_permission_is_denied(
    organization_role: str | None, project_role: str | None, status: str
) -> None:
    assert not resolve_project_actions(organization_role, project_role, status)


@pytest.mark.parametrize(
    ("org_role", "project_role"),
    [
        ("owner", None),
        ("admin", None),
        ("member", "manager"),
        ("member", "editor"),
        ("member", "viewer"),
    ],
)
def test_archived_is_read_only(org_role: str, project_role: str | None) -> None:
    assert resolve_project_actions(org_role, project_role, "archived") == {Action.VIEW}
