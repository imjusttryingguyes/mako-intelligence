"""Local-only, non-secret Yandex Direct client-to-project binding.

This does NOT authenticate or sync the provider account. There are no tokens,
OAuth callbacks, Yandex API requests or persistent integrations here.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from mako_intelligence.api.routes.auth import _require_origin, authenticated_user
from mako_intelligence.api.routes.projects import _organization_membership
from mako_intelligence.db.models import Project, ProjectDirectBinding, ProjectEvent, User
from mako_intelligence.db.session import get_db

router = APIRouter(tags=["direct-bindings"])


class BindingInput(BaseModel):
    # Refuse unexpected values, including an accidental OAuth token field.
    model_config = ConfigDict(extra="forbid")
    client_login: str = Field(
        min_length=1,
        max_length=255,
        pattern=r"^[A-Za-z0-9][A-Za-z0-9._@-]{0,254}$",
    )


def _project_for_admin(
    db: Session,
    *,
    user_id: uuid.UUID,
    organization_id: uuid.UUID,
    project_id: uuid.UUID,
    lock: bool = False,
) -> Project:
    role = _organization_membership(db, user_id, organization_id)
    if role not in ("owner", "admin"):
        raise HTTPException(status_code=403, detail="insufficient permissions")
    stmt = select(Project).where(
        Project.organization_id == organization_id,
        Project.id == project_id,
    )
    if lock:
        stmt = stmt.with_for_update()
    project = db.scalar(stmt)
    if project is None:
        raise HTTPException(status_code=404, detail="not found")
    return project


def _binding_view(binding: ProjectDirectBinding | None) -> dict:
    return {
        "provider": "yandex_direct",
        "client_login": binding.client_login if binding is not None else None,
        "status": "configured_unverified" if binding is not None else "not_configured",
    }


@router.get("/organizations/{organization_id}/projects/{project_id}/direct-binding")
def read_binding(
    organization_id: uuid.UUID,
    project_id: uuid.UUID,
    user: User = Depends(authenticated_user),
    db: Session = Depends(get_db),
) -> dict:
    _project_for_admin(
        db, user_id=user.id, organization_id=organization_id, project_id=project_id,
    )
    binding = db.get(ProjectDirectBinding, project_id)
    if binding is not None and binding.organization_id != organization_id:
        raise HTTPException(status_code=404, detail="not found")
    return _binding_view(binding)


@router.put("/organizations/{organization_id}/projects/{project_id}/direct-binding")
def save_binding(
    organization_id: uuid.UUID,
    project_id: uuid.UUID,
    payload: BindingInput,
    request: Request,
    user: User = Depends(authenticated_user),
    db: Session = Depends(get_db),
) -> dict:
    _require_origin(request)
    project = _project_for_admin(
        db, user_id=user.id, organization_id=organization_id,
        project_id=project_id, lock=True,
    )
    if project.status != "active":
        raise HTTPException(status_code=409, detail="archived project is read-only")

    binding = db.get(ProjectDirectBinding, project_id)
    if binding is not None and binding.organization_id != organization_id:
        raise HTTPException(status_code=404, detail="not found")

    previous = binding.client_login if binding is not None else None
    if previous != payload.client_login:
        if binding is None:
            binding = ProjectDirectBinding(
                project_id=project_id,
                organization_id=organization_id,
                client_login=payload.client_login,
                status="configured_unverified",
            )
            db.add(binding)
        else:
            binding.client_login = payload.client_login
            binding.status = "configured_unverified"
            binding.updated_at = datetime.now(timezone.utc)

        # Does not create a connection or authorize a client. Audited metadata only.
        db.add(ProjectEvent(
            organization_id=organization_id, project_id=project_id,
            actor_user_id=user.id, action="direct_bind",
            old_client_login=previous, new_client_login=payload.client_login,
        ))
        db.commit()

    return _binding_view(binding)


@router.delete("/organizations/{organization_id}/projects/{project_id}/direct-binding",
               status_code=204)
def remove_binding(
    organization_id: uuid.UUID,
    project_id: uuid.UUID,
    request: Request,
    user: User = Depends(authenticated_user),
    db: Session = Depends(get_db),
) -> None:
    _require_origin(request)
    project = _project_for_admin(
        db, user_id=user.id, organization_id=organization_id,
        project_id=project_id, lock=True,
    )
    if project.status != "active":
        raise HTTPException(status_code=409, detail="archived project is read-only")

    binding = db.get(ProjectDirectBinding, project_id)
    if binding is None or binding.organization_id != organization_id:
        raise HTTPException(status_code=404, detail="not found")

    db.add(ProjectEvent(
        organization_id=organization_id, project_id=project_id,
        actor_user_id=user.id, action="direct_unbind",
        old_client_login=binding.client_login,
    ))
    db.delete(binding)
    db.commit()
