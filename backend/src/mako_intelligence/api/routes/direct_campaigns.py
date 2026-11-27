"""Manual, bounded and read-only Direct campaign inventory preview.

No campaign rows are persisted. Authorization is verified before AND after
the upstream request. This is a local-only development endpoint, not a sync job.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from sqlalchemy import select
from sqlalchemy.orm import Session

from mako_intelligence.api.routes.auth import _require_origin, authenticated_user
from mako_intelligence.api.routes.direct_bindings import _project_for_admin
from mako_intelligence.db.models import (
    OrganizationDirectCredential,
    ProjectDirectBinding,
    User,
)
from mako_intelligence.db.session import get_db
from mako_intelligence.integrations.direct_vault import (
    DirectVault,
    DirectVaultError,
    load_vault_key,
)
from mako_intelligence.integrations.yandex_direct import DirectReadClient, DirectReadError

router = APIRouter(tags=["direct-campaign-preview"])
MAX_VERIFICATION_AGE = timedelta(hours=24)
MAX_CAMPAIGNS = 1000
MAX_NAME_LENGTH = 255


@router.post("/organizations/{organization_id}/projects/{project_id}/direct-campaign-preview")
def preview_direct_campaigns(
    organization_id: uuid.UUID,
    project_id: uuid.UUID,
    request: Request,
    response: Response,
    user: User = Depends(authenticated_user),
    db: Session = Depends(get_db),
) -> dict:
    """Preview names/IDs for a recently verified advertiser (admin-only)."""
    _require_origin(request)
    response.headers["Cache-Control"] = "no-store"
    project = _project_for_admin(
        db, user_id=user.id, organization_id=organization_id, project_id=project_id,
    )
    if project.status != "active":
        raise HTTPException(status_code=409, detail="archived project is read-only")

    binding = db.get(ProjectDirectBinding, project_id)
    if binding is None or binding.organization_id != organization_id:
        raise HTTPException(status_code=409, detail="configure a Direct client login first")
    credential = db.get(OrganizationDirectCredential, organization_id)
    if credential is None:
        raise HTTPException(status_code=409, detail="agency token is not available")

    now = datetime.now(timezone.utc)
    if (
        binding.verified_at is None
        or binding.verified_token_revision != credential.revision
        or binding.verified_at < now - MAX_VERIFICATION_AGE
    ):
        raise HTTPException(status_code=409, detail="verify advertiser access again")

    login = binding.client_login
    revision = credential.revision
    verified_at = binding.verified_at

    try:
        token = DirectVault(load_vault_key()).open(credential.encrypted_token, organization_id)
        with DirectReadClient(token) as direct:
            provider_rows = direct.get_campaigns(client_login=login)
    except DirectVaultError:
        raise HTTPException(status_code=503, detail="local Direct credential unavailable") from None
    except (DirectReadError, ValueError) as exc:
        code = (
            f" (code {exc.error_code})"
            if isinstance(exc, DirectReadError) and exc.error_code is not None
            else ""
        )
        raise HTTPException(
            status_code=502, detail=f"Yandex Direct read-only request failed{code}"
        ) from None

    if len(provider_rows) > MAX_CAMPAIGNS:
        raise HTTPException(status_code=502, detail="Direct campaign preview limit exceeded")

    items: list[dict] = []
    for row in provider_rows:
        if not isinstance(row, dict):
            raise HTTPException(status_code=502, detail="Invalid Direct campaign response")
        campaign_id = row.get("Id")
        name = row.get("Name")
        if (
            type(campaign_id) is not int
            or campaign_id <= 0
            or not isinstance(name, str)
            or not name
            or len(name) > MAX_NAME_LENGTH
        ):
            raise HTTPException(status_code=502, detail="Invalid Direct campaign response")
        items.append({"id": campaign_id, "name": name})

    items.sort(key=lambda item: (item["name"].casefold(), item["id"]))

    # User and binding can change during a slow upstream request. Recheck before
    # returning sensitive campaign names, not just before a database write.
    project = _project_for_admin(
        db, user_id=user.id, organization_id=organization_id, project_id=project_id,
        lock=True,
    )
    latest = db.scalar(
        select(ProjectDirectBinding)
        .where(
            ProjectDirectBinding.project_id == project_id,
            ProjectDirectBinding.organization_id == organization_id,
        )
        .with_for_update()
        .execution_options(populate_existing=True)
    )
    latest_credential = db.scalar(
        select(OrganizationDirectCredential)
        .where(OrganizationDirectCredential.organization_id == organization_id)
        .execution_options(populate_existing=True)
    )
    if (
        project.status != "active"
        or latest is None
        or latest.client_login != login
        or latest.verified_at != verified_at
        or latest_credential is None
        or latest_credential.revision != revision
    ):
        db.rollback()
        raise HTTPException(status_code=409, detail="Direct account configuration changed")

    retrieved_at = datetime.now(timezone.utc).isoformat()
    db.rollback()  # Read-only: release row locks without any write.
    return {
        "count": len(items),
        "fetched_at": retrieved_at,
        "campaigns": items,
    }
