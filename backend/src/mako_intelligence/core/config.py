"""Local-development configuration; never log secrets or database connection URLs."""
import os


def frontend_origin() -> str:
    return os.getenv("FRONTEND_ORIGIN", "http://localhost:3000")


def database_url() -> str | None:
    return os.getenv("DATABASE_URL")


def local_auth_enabled() -> bool:
    # Explicit opt-in. Must remain off in nonlocal environments.
    return os.getenv("MAKO_LOCAL_AUTH_ENABLED") == "1"
