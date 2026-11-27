"""Deliberately tiny configuration layer for Milestone A.

When authentication and tokens arrive, replace with typed environment settings.
Never log secret-bearing environment variables.
"""
import os


def frontend_origin() -> str:
    return os.getenv("FRONTEND_ORIGIN", "http://localhost:3000")


def database_url() -> str | None:
    return os.getenv("DATABASE_URL")
