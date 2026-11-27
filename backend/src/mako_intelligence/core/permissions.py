"""Fail-closed project authorization rules and tenant-scoped read queries.

IMPORTANT: The caller's user_id must come from a VERIFIED server-side session.
Never take it from untrusted request parameters or an HTTP header.

This module intentionally exposes no API routes; login/session handling is B2.2.
"""
from __future__ import annotations

import uuid
from dataclasses import dataclass
from enum import StrEnum

from sqlalchemy import and_, or_, select
from sqlalchemy.orm import Session

from mako_intelligence.db.models import OrganizationMembership, Project, ProjectMembership


class ProjectAction(StrEnum):
    VIEW = "view"
    EDIT = "edit"
    MANAGE_MEMBERS = "manage_members"


@dataclass(frozen=True, slots=True)
class VisibleProject:
    id: uuid.UUID
    slug: str
    name: str
    status: str
    actions: frozenset[ProjectAction]


_NO_ACCESS: frozenset[ProjectAction] = frozenset()
_VIEW = frozenset({ProjectAction.VIEW})
_EDIT = frozenset({ProjectAction.VIEW, ProjectAction.EDIT})
_MANAGE = frozenset({
    ProjectAction.VIEW,
    ProjectAction.EDIT,
    ProjectAction.MANAGE_MEMBERS,
})

_PROJECT_ROLES = {
    "manager": _MANAGE,
    "editor": _EDIT,
    "viewer": _VIEW,
}


def resolve_project_actions(
    organization_role: str | None,
    project_role: str | None,
    project_status: str,
) -> frozenset[ProjectAction]:
    """Return effective permissions, defaulting to deny for unknown states.

    Org owners/admins inherit access to *their organization's* projects.
    Org members must have an explicit project membership. Archived projects
    are read-only for everyone; restoring is a separate future admin action.
    """
    if project_status not in ("active", "archived"):
        return _NO_ACCESS
    if organization_role in ("owner", "admin"):
        actions = _MANAGE
    elif organization_role == "member":
        actions = _PROJECT_ROLES.get(project_role, _NO_ACCESS)
    else:
        return _NO_ACCESS

    if project_status == "archived":
        return _VIEW if ProjectAction.VIEW in actions else _NO_ACCESS
    return actions


def project_permissions(
    session: Session,
    *,
    user_id: uuid.UUID,
    organization_id: uuid.UUID,
    project_id: uuid.UUID,
) -> frozenset[ProjectAction]:
    """Lookup MUST be scoped by organization and authenticated user identity.

    Missing membership, missing project and cross-org IDs all return empty
    permissions. This avoids disclosing a project's existence to outsiders.
    """
    query = (
        select(Project.status, OrganizationMembership.role, ProjectMembership.role)
        .select_from(Project)
        .join(
            OrganizationMembership,
            and_(
                OrganizationMembership.organization_id == Project.organization_id,
                OrganizationMembership.user_id == user_id,
            ),
        )
        .outerjoin(
            ProjectMembership,
            and_(
                ProjectMembership.organization_id == Project.organization_id,
                ProjectMembership.project_id == Project.id,
                ProjectMembership.user_id == user_id,
            ),
        )
        .where(Project.id == project_id, Project.organization_id == organization_id)
    )
    row = session.execute(query).one_or_none()
    if row is None:
        return _NO_ACCESS
    status, org_role, project_role = row
    return resolve_project_actions(org_role, project_role, status)


def visible_projects(
    session: Session, *, user_id: uuid.UUID, organization_id: uuid.UUID
) -> list[VisibleProject]:
    """Return only projects visible to this user within this organization."""
    query = (
        select(
            Project.id,
            Project.slug,
            Project.name,
            Project.status,
            OrganizationMembership.role,
            ProjectMembership.role,
        )
        .select_from(Project)
        .join(
            OrganizationMembership,
            and_(
                OrganizationMembership.organization_id == Project.organization_id,
                OrganizationMembership.user_id == user_id,
            ),
        )
        .outerjoin(
            ProjectMembership,
            and_(
                ProjectMembership.organization_id == Project.organization_id,
                ProjectMembership.project_id == Project.id,
                ProjectMembership.user_id == user_id,
            ),
        )
        .where(
            Project.organization_id == organization_id,
            or_(
                OrganizationMembership.role.in_(("owner", "admin")),
                ProjectMembership.user_id.is_not(None),
            ),
        )
        .order_by(Project.name, Project.id)
    )
    result: list[VisibleProject] = []
    for project_id, slug, name, status, org_role, project_role in session.execute(query):
        actions = resolve_project_actions(org_role, project_role, status)
        if actions:
            result.append(
                VisibleProject(
                    id=project_id,
                    slug=slug,
                    name=name,
                    status=status,
                    actions=actions,
                )
            )
    return result
