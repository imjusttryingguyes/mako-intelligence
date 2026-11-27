"""Read-only tenant-scoped endpoints. No caller-supplied identity."""
from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from mako_intelligence.api.routes.auth import authenticated_user
from mako_intelligence.core.permissions import project_permissions, visible_projects
from mako_intelligence.db.models import Organization, OrganizationMembership, Project, User
from mako_intelligence.db.session import get_db

router = APIRouter(tags=["projects"])


def _organization_membership(db: Session, user_id: uuid.UUID, organization_id: uuid.UUID) -> None:
    role = db.scalar(
        select(OrganizationMembership.role).where(
            OrganizationMembership.organization_id == organization_id,
            OrganizationMembership.user_id == user_id,
        )
    )
    if role not in ("owner", "admin", "member"):
        raise HTTPException(status_code=404, detail="not found")


@router.get("/organizations")
def organizations(
    user: User = Depends(authenticated_user),
    db: Session = Depends(get_db),
) -> list[dict]:
    stmt = (
        select(Organization, OrganizationMembership.role)
        .join(
            OrganizationMembership,
            OrganizationMembership.organization_id == Organization.id,
        )
        .where(OrganizationMembership.user_id == user.id)
        .order_by(Organization.name)
    )
    return [
        {"id": str(org.id), "slug": org.slug, "name": org.name, "role": role}
        for org, role in db.execute(stmt)
        if role in ("owner", "admin", "member")
    ]


@router.get("/organizations/{organization_id}/projects")
def list_projects(
    organization_id: uuid.UUID,
    user: User = Depends(authenticated_user),
    db: Session = Depends(get_db),
) -> list[dict]:
    _organization_membership(db, user.id, organization_id)
    return [
        {
            "id": str(project.id),
            "slug": project.slug,
            "name": project.name,
            "status": project.status,
            "actions": sorted(action.value for action in project.actions),
        }
        for project in visible_projects(db, user_id=user.id, organization_id=organization_id)
    ]


@router.get("/organizations/{organization_id}/projects/{project_id}")
def project_detail(
    organization_id: uuid.UUID,
    project_id: uuid.UUID,
    user: User = Depends(authenticated_user),
    db: Session = Depends(get_db),
) -> dict:
    actions = project_permissions(
        db, user_id=user.id, organization_id=organization_id, project_id=project_id,
    )
    if not actions:
        raise HTTPException(status_code=404, detail="not found")
    project = db.scalar(
        select(Project).where(
            Project.organization_id == organization_id,
            Project.id == project_id,
        )
    )
    if project is None:
        raise HTTPException(status_code=404, detail="not found")
    return {
        "id": str(project.id),
        "slug": project.slug,
        "name": project.name,
        "status": project.status,
        "actions": sorted(action.value for action in actions),
    }
