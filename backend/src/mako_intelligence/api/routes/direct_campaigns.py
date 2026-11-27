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
from mako_intelligence.integrations.yandex_reports import DirectReportsClient

router = APIRouter(tags=["direct-campaign-preview"])
MAX_VERIFICATION_AGE = timedelta(hours=24)
MAX_CAMPAIGNS = 2000
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
        # Reports is a separate read-only API with different campaign coverage.
        # A queued or failed report is surfaced explicitly, NOT an empty list.
        report_status = "unavailable"
        report_rows: list[dict] = []
        try:
            with DirectReportsClient(token) as reports:
                report = reports.get_campaigns_with_statistics(client_login=login)
            report_status = report.status
            report_rows = report.campaigns
        except (DirectReadError, ValueError):
            report_status = "unavailable"
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

    inventory: dict[int, dict] = {}
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
        if campaign_id in inventory:
            raise HTTPException(status_code=502, detail="Duplicate Direct campaign ID")
        inventory[campaign_id] = {
            "id": campaign_id, "name": name, "type": None, "source": "campaigns",
        }

    report_only = 0
    if report_status == "ready":
        for row in report_rows:
            campaign_id = row["id"]
            if campaign_id in inventory:
                inventory[campaign_id]["source"] = "both"
                inventory[campaign_id]["type"] = row["type"]
            else:
                report_only += 1
                inventory[campaign_id] = {
                    "id": campaign_id,
                    "name": row["name"],
                    "type": row["type"],
                    "source": "reports",
                }
    if len(inventory) > MAX_CAMPAIGNS:
        raise HTTPException(status_code=502, detail="Combined campaign preview limit exceeded")
    items = sorted(inventory.values(), key=lambda item: (item["name"].casefold(), item["id"]))

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
        "campaigns_get_count": len(provider_rows),
        "reports_only_count": report_only,
        "report_status": report_status,
        "report_period": "LAST_365_DAYS",
        "completeness": "period_limited" if report_status == "ready" else "incomplete",
        "fetched_at": retrieved_at,
        "campaigns": items,
    }
