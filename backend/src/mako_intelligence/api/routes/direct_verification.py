"""Local-only read-only account verification with server-held encrypted OAuth.

Only the project owner's organization can invoke verification. No OAuth
token, campaign names or agency client list is returned to the browser.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy import select
from sqlalchemy.orm import Session

from mako_intelligence.api.routes.auth import _require_origin, authenticated_user
from mako_intelligence.api.routes.direct_bindings import _binding_view, _project_for_admin
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

router = APIRouter(tags=["direct-verification"])
VERIFY_COOLDOWN = timedelta(seconds=60)


@router.post("/organizations/{organization_id}/projects/{project_id}/direct-verify")
def verify_project_direct_account(
    organization_id: uuid.UUID,
    project_id: uuid.UUID,
    request: Request,
    user: User = Depends(authenticated_user),
    db: Session = Depends(get_db),
) -> dict:
    """Manually verify agency client membership and read a bounded campaign count."""
    _require_origin(request)
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
        raise HTTPException(status_code=409, detail="agency token not imported locally")

    now = datetime.now(timezone.utc)
    if (binding.verified_at is not None
        and binding.verified_token_revision == credential.revision
        and binding.verified_at + VERIFY_COOLDOWN > now):
        return _binding_view(binding, credential)

    verified_login = binding.client_login
    credential_revision = credential.revision
    try:
        token = DirectVault(load_vault_key()).open(credential.encrypted_token, organization_id)
        with DirectReadClient(token) as direct:
            clients = direct.get_agency_clients()
            accessible = any(
                isinstance(client.get("Login"), str)
                and client["Login"].casefold() == verified_login.casefold()
                for client in clients
            )
            if not accessible:
                raise HTTPException(
                    status_code=403, detail="advertiser is not in accessible agency clients"
                )
            campaigns = direct.get_campaigns(client_login=verified_login)
    except DirectVaultError:
        raise HTTPException(status_code=503, detail="local Direct credential unavailable") from None
    except DirectReadError as exc:
        # Only a numeric provider code is safe to expose; no upstream body or secrets.
        code = f" (code {exc.error_code})" if exc.error_code is not None else ""
        raise HTTPException(
            status_code=502, detail=f"Yandex Direct read-only check failed{code}"
        ) from None

    # Re-check mutable data after the network operation to avoid committing a
    # successful state for a project/credential that was changed mid-request.
    project = _project_for_admin(
        db, user_id=user.id, organization_id=organization_id, project_id=project_id,
        lock=True,
    )
    current = db.scalar(
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
        or current is None
        or current.client_login != verified_login
        or latest_credential is None
        or latest_credential.revision != credential_revision
    ):
        db.rollback()
        raise HTTPException(status_code=409, detail="project or agency credentials changed")

    current.verified_at = datetime.now(timezone.utc)
    current.verified_campaign_count = len(campaigns)
    current.verified_token_revision = credential_revision
    db.commit()
    return _binding_view(current, latest_credential)
