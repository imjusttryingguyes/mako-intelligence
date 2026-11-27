"""Tenant-scoped project endpoints. Never accept caller-supplied user identity."""
from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field, field_validator
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from mako_intelligence.api.routes.auth import _require_origin, authenticated_user
from mako_intelligence.core.permissions import project_permissions, visible_projects
from mako_intelligence.db.models import (
    Organization,
    OrganizationMembership,
    Project,
    ProjectEvent,
    User,
)
from mako_intelligence.db.session import get_db

router = APIRouter(tags=["projects"])


def _organization_membership(db: Session, user_id: uuid.UUID, organization_id: uuid.UUID) -> str:
    role = db.scalar(
        select(OrganizationMembership.role).where(
            OrganizationMembership.organization_id == organization_id,
            OrganizationMembership.user_id == user_id,
        )
    )
    if role not in ("owner", "admin", "member"):
        raise HTTPException(status_code=404, detail="not found")
    return role


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




class NewProjectInput(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    slug: str = Field(
        min_length=3,
        max_length=80,
        pattern=r"^[a-z0-9][a-z0-9-]{1,78}[a-z0-9]$",
    )

    @field_validator("name")
    @classmethod
    def nonempty_name(cls, value: str) -> str:
        name = value.strip()
        if not name:
            raise ValueError("Project name cannot be blank")
        return name


@router.post("/organizations/{organization_id}/projects", status_code=201)
def create_project(
    organization_id: uuid.UUID,
    payload: NewProjectInput,
    request: Request,
    user: User = Depends(authenticated_user),
    db: Session = Depends(get_db),
) -> dict:
    """Create an empty project in an organization owned/administered by this user.

    Server identity comes exclusively from the authenticated session cookie.
    Members and outsiders are denied regardless of submitted organization UUID.
    """
    _require_origin(request)
    role = _organization_membership(db, user.id, organization_id)
    if role not in ("owner", "admin"):
        raise HTTPException(status_code=403, detail="insufficient permissions")

    duplicate = db.scalar(
        select(Project.id).where(
            Project.organization_id == organization_id,
            Project.slug == payload.slug,
        )
    )
    if duplicate is not None:
        raise HTTPException(status_code=409, detail="project code already exists")

    project = Project(
        id=uuid.uuid4(),
        organization_id=organization_id,
        slug=payload.slug,
        name=payload.name,
        status="active",
    )
    db.add(project)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        # A simultaneous create may have won the unique (org_id, slug) constraint.
        raise HTTPException(status_code=409, detail="project code already exists") from None

    actions = project_permissions(
        db, user_id=user.id, organization_id=organization_id, project_id=project.id
    )
    return {
        "id": str(project.id),
        "slug": project.slug,
        "name": project.name,
        "status": project.status,
        "actions": sorted(action.value for action in actions),
    }



class RenameProjectInput(BaseModel):
    name: str = Field(min_length=1, max_length=200)

    @field_validator("name")
    @classmethod
    def normalized_name(cls, value: str) -> str:
        name = value.strip()
        if not name:
            raise ValueError("Project name cannot be blank")
        return name


@router.patch("/organizations/{organization_id}/projects/{project_id}")
def rename_project(
    organization_id: uuid.UUID,
    project_id: uuid.UUID,
    payload: RenameProjectInput,
    request: Request,
    user: User = Depends(authenticated_user),
    db: Session = Depends(get_db),
) -> dict:
    """Rename an active project. This is an org-admin metadata operation.

    This endpoint never modifies the project's immutable UUID, code or tenant.
    Project-level manager/editor roles deliberately cannot rename project identity.
    """
    _require_origin(request)
    role = _organization_membership(db, user.id, organization_id)
    if role not in ("owner", "admin"):
        raise HTTPException(status_code=403, detail="insufficient permissions")

    project = db.scalar(
        select(Project).where(
            Project.organization_id == organization_id, Project.id == project_id
        ).with_for_update()
    )
    if project is None:
        raise HTTPException(status_code=404, detail="not found")
    if project.status != "active":
        raise HTTPException(status_code=409, detail="archived project is read-only")

    if project.name != payload.name:
        old_name = project.name
        project.name = payload.name
        db.add(ProjectEvent(
            organization_id=organization_id,
            project_id=project.id,
            actor_user_id=user.id,
            action="rename",
            old_name=old_name,
            new_name=payload.name,
        ))
        db.commit()
    return {
        "id": str(project.id),
        "slug": project.slug,
        "name": project.name,
        "status": project.status,
        "actions": sorted(
            action.value
            for action in project_permissions(
                db, user_id=user.id, organization_id=organization_id, project_id=project.id
            )
        ),
    }



def _change_project_status(
    *,
    organization_id: uuid.UUID,
    project_id: uuid.UUID,
    user: User,
    db: Session,
    action: str,
) -> dict:
    role = _organization_membership(db, user.id, organization_id)
    if role not in ("owner", "admin"):
        raise HTTPException(status_code=403, detail="insufficient permissions")

    # Serialize competing state changes so double archive/restore cannot both succeed.
    project = db.scalar(
        select(Project).where(
            Project.organization_id == organization_id, Project.id == project_id
        ).with_for_update()
    )
    if project is None:
        raise HTTPException(status_code=404, detail="not found")
    old_status = "active" if action == "archive" else "archived"
    new_status = "archived" if action == "archive" else "active"
    if project.status != old_status:
        raise HTTPException(status_code=409, detail="project status already changed")
    project.status = new_status
    db.add(ProjectEvent(
        organization_id=organization_id,
        project_id=project_id,
        actor_user_id=user.id,
        action=action,
        old_status=old_status,
        new_status=new_status,
    ))
    db.commit()

    actions = project_permissions(
        db, user_id=user.id, organization_id=organization_id, project_id=project.id
    )
    return {
        "id": str(project.id),
        "slug": project.slug,
        "name": project.name,
        "status": project.status,
        "actions": sorted(action.value for action in actions),
    }


@router.post("/organizations/{organization_id}/projects/{project_id}/archive")
def archive_project(
    organization_id: uuid.UUID,
    project_id: uuid.UUID,
    request: Request,
    user: User = Depends(authenticated_user),
    db: Session = Depends(get_db),
) -> dict:
    _require_origin(request)
    return _change_project_status(
        organization_id=organization_id, project_id=project_id,
        user=user, db=db, action="archive",
    )


@router.post("/organizations/{organization_id}/projects/{project_id}/restore")
def restore_project(
    organization_id: uuid.UUID,
    project_id: uuid.UUID,
    request: Request,
    user: User = Depends(authenticated_user),
    db: Session = Depends(get_db),
) -> dict:
    _require_origin(request)
    return _change_project_status(
        organization_id=organization_id, project_id=project_id,
        user=user, db=db, action="restore",
    )


@router.get("/organizations/{organization_id}/projects/{project_id}/history")
def project_history(
    organization_id: uuid.UUID,
    project_id: uuid.UUID,
    user: User = Depends(authenticated_user),
    db: Session = Depends(get_db),
) -> list[dict]:
    role = _organization_membership(db, user.id, organization_id)
    if role not in ("owner", "admin"):
        raise HTTPException(status_code=403, detail="insufficient permissions")
    found = db.scalar(
        select(Project.id).where(
            Project.organization_id == organization_id, Project.id == project_id
        )
    )
    if found is None:
        raise HTTPException(status_code=404, detail="not found")

    stmt = (
        select(ProjectEvent, User.display_name)
        .join(User, User.id == ProjectEvent.actor_user_id)
        .where(
            ProjectEvent.organization_id == organization_id,
            ProjectEvent.project_id == project_id,
        )
        .order_by(ProjectEvent.created_at.desc(), ProjectEvent.id.desc())
        .limit(100)
    )
    return [
        {
            "id": str(event.id),
            "action": event.action,
            "actor": actor_name,
            "actor_id": str(event.actor_user_id),
            "old_name": event.old_name,
            "new_name": event.new_name,
            "old_status": event.old_status,
            "new_status": event.new_status,
            "old_client_login": event.old_client_login,
            "new_client_login": event.new_client_login,
            "created_at": event.created_at.isoformat(),
        }
        for event, actor_name in db.execute(stmt)
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
