"""Database probe, not a data layer (data models start in Milestone B)."""

from sqlalchemy import create_engine, text

from mako.core.config import database_url


def check_database() -> None:
    url = database_url()
    if not url:
        raise RuntimeError("DATABASE_URL is not configured")
    engine = create_engine(url, connect_args={"connect_timeout": 2}, pool_pre_ping=True)
    try:
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
    finally:
        engine.dispose()
