import logging

from fastapi import APIRouter, HTTPException

from mako import __version__
from mako.db.connection import check_database

router = APIRouter(tags=["health"])
logger = logging.getLogger(__name__)


@router.get("/healthz")
def healthz() -> dict[str, str]:
    """Liveness: process is responsive even if the database is down."""
    return {"status": "ok", "service": "mako-api", "version": __version__}


@router.get("/readyz")
def readyz() -> dict[str, str]:
    """Readiness: database is reachable. Never reveal credentials/errors."""
    try:
        check_database()
    except Exception:
        logger.warning("Database readiness check failed")
        raise HTTPException(status_code=503, detail="database unavailable") from None
    return {"status": "ready", "database": "ok"}
