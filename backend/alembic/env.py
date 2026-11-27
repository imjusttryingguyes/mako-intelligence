"""Run database migrations manually, not during API startup."""
from alembic import context
from sqlalchemy import create_engine, pool

from mako_intelligence.core.config import database_url
from mako_intelligence.db.models import Base

config = context.config
target_metadata = Base.metadata


def run_migrations_online() -> None:
    url = database_url()
    if not url:
        raise RuntimeError("DATABASE_URL is required for migrations")
    engine = create_engine(url, poolclass=pool.NullPool)
    try:
        with engine.connect() as connection:
            context.configure(
                connection=connection,
                target_metadata=target_metadata,
                compare_type=True,
            )
            with context.begin_transaction():
                context.run_migrations()
    finally:
        engine.dispose()


run_migrations_online()
