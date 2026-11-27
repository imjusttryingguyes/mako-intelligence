"""Interactive ONE-TIME local owner bootstrap.

Run in a VS Code Docker terminal:
    docker compose exec backend python -m mako_intelligence.tools.bootstrap_local_owner

No password is ever passed via CLI flags, environment, GitHub or logs.
"""
from __future__ import annotations

import getpass
import re
import uuid

from sqlalchemy import select
from sqlalchemy.orm import Session

from mako_intelligence.core.auth import hash_password
from mako_intelligence.core.config import local_auth_enabled
from mako_intelligence.db.models import (
    LocalCredential,
    Organization,
    OrganizationMembership,
    Project,
    User,
)
from mako_intelligence.db.session import get_engine


def bootstrap_local_owner(email: str, display_name: str, password: str) -> None:
    if not local_auth_enabled():
        raise RuntimeError("Local auth must be explicitly enabled")
    email = email.strip().casefold()
    display_name = display_name.strip()
    if not (3 <= len(email) <= 320 and re.fullmatch(r"[^\s@]+@[^\s@]+\.[^\s@]+", email)):
        raise ValueError("Enter a valid email address")
    if not 1 <= len(display_name) <= 200:
        raise ValueError("Display name must have 1–200 characters")

    password_hash = hash_password(password)
    with Session(get_engine()) as db, db.begin():
        if db.scalar(select(Organization.id).limit(1)) or db.scalar(select(User.id).limit(1)):
            raise RuntimeError(
                "Bootstrap refused: users or organizations already exist. "
                "Do not reset an existing installation."
            )
        org = Organization(
            id=uuid.uuid4(), slug="mako", name="MAKO Intelligence",
        )
        user = User(id=uuid.uuid4(), email=email, display_name=display_name)
        db.add_all([org, user])
        db.flush()
        db.add_all([
            LocalCredential(user_id=user.id, password_hash=password_hash),
            OrganizationMembership(organization_id=org.id, user_id=user.id, role="owner"),
            Project(
                id=uuid.uuid4(), organization_id=org.id,
                slug="demo", name="Демо-проект", status="active",
            ),
        ])
    print("Создан локальный владелец MAKO и пустой демонстрационный проект.")
    print("Пароль не сохранялся в истории команд. Можно войти через localhost:3000.")


def main() -> None:
    print("Локальная первичная настройка MAKO Intelligence")
    email = input("Электронная почта для входа: ").strip()
    name = input("Отображаемое имя: ").strip()
    password = getpass.getpass("Пароль (не менее 12 символов): ")
    password_again = getpass.getpass("Повторите пароль: ")
    if password != password_again:
        raise SystemExit("Пароли не совпадают. Ничего не изменено.")
    try:
        bootstrap_local_owner(email, name, password)
    except (RuntimeError, ValueError) as exc:
        raise SystemExit(str(exc)) from None


if __name__ == "__main__":
    main()
