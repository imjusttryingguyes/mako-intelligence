"""Local PostgreSQL dependency; do not log database URLs or credentials."""
from __future__ import annotations

from functools import lru_cache
from typing import Iterator

from fastapi import HTTPException
from sqlalchemy import Engine, create_engine
from sqlalchemy.orm import Session

from mako_intelligence.core.config import database_url


@lru_cache(maxsize=1)
def get_engine() -> Engine:
    url = database_url()
    if not url:
        raise RuntimeError("DATABASE_URL must be configured")
    return create_engine(url, pool_pre_ping=True)


def get_db() -> Iterator[Session]:
    try:
        engine = get_engine()
        with Session(engine) as db:
            yield db
    except RuntimeError:
        raise HTTPException(status_code=503, detail="database unavailable") from None
