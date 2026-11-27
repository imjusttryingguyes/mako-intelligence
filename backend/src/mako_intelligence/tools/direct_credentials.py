"""Explicit local agency OAuth token import/revoke; never put secrets in argv/env.

Commands:
  docker compose exec backend python -m mako_intelligence.tools.direct_credentials import
  docker compose exec backend python -m mako_intelligence.tools.direct_credentials remove

Requires the MAKO organization owner/admin email + password and an already
initialized separate Direct key volume. OAuth is manual here, not a browser flow.
"""
from __future__ import annotations

import getpass
import sys
from datetime import datetime, timezone

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from mako_intelligence.core.auth import verify_password
from mako_intelligence.db.models import (
    LocalCredential,
    Organization,
    OrganizationDirectCredential,
    OrganizationMembership,
    User,
)
from mako_intelligence.db.session import get_engine
from mako_intelligence.integrations.direct_vault import (
    DirectVault,
    DirectVaultError,
    load_vault_key,
)
from mako_intelligence.integrations.yandex_direct import DirectReadClient, DirectReadError
from mako_intelligence.tools.yandex_direct_probe import prompt_for_token


def authorized_organization(db: Session) -> Organization:
    slug = input("Код организации MAKO (обычно mako): ").strip()
    email = input("Почта владельца/администратора MAKO: ").strip().casefold()
    password = getpass.getpass("Пароль от MAKO (ввод скрыт): ")

    org = db.scalar(select(Organization).where(Organization.slug == slug))
    user = db.scalar(select(User).where(func.lower(User.email) == email))
    credential = db.get(LocalCredential, user.id) if user is not None else None
    role = db.scalar(select(OrganizationMembership.role).where(
        OrganizationMembership.organization_id == org.id,
        OrganizationMembership.user_id == user.id,
    )) if org is not None and user is not None else None

    if role not in ("owner", "admin") or credential is None or not verify_password(
        password, credential.password_hash
    ):
        raise ValueError("Неверные данные MAKO или недостаточно прав")
    return org


def import_token(db: Session, org: Organization, vault: DirectVault) -> None:
    token = prompt_for_token()
    # Prove the token belongs to an authorized agency before any database write.
    try:
        with DirectReadClient(token) as direct:
            clients = direct.get_agency_clients()
    except DirectReadError as exc:
        raise ValueError(
            f"Директ отклонил проверку агентского доступа: {exc}"
        ) from None

    record = db.get(OrganizationDirectCredential, org.id)
    blob = vault.seal(token, org.id)
    if record is None:
        db.add(OrganizationDirectCredential(
            organization_id=org.id, encrypted_token=blob, revision=1,
        ))
        print(f"Агентский доступ проверен: {len(clients)} клиентов. Новый токен сохранён зашифрованным.")
    else:
        record.encrypted_token = blob
        record.revision += 1
        record.updated_at = datetime.now(timezone.utc)
        print(
            f"Агентский доступ проверен: {len(clients)} клиентов. "
            "Токен заменён; прежние проверки проектов требуют повторения."
        )
    db.commit()


def remove_token(db: Session, org: Organization) -> None:
    record = db.get(OrganizationDirectCredential, org.id)
    if record is None:
        print("В MAKO нет сохранённого токена для этой организации.")
        return
    answer = input(f"Для удаления локального токена введи код организации «{org.slug}»: ").strip()
    if answer != org.slug:
        raise ValueError("Удаление отменено: код организации не совпадает")
    db.delete(record)
    db.commit()
    print("Локальный зашифрованный токен удалён из MAKO.")
    print("Это НЕ отзыв токена в Яндекс OAuth. Для полного отзыва отключи доступ и в Яндексе.")


def main() -> None:
    mode = sys.argv[1:]  # Only a subcommand; tokens/passwords never accepted as args.
    if mode not in (["import"], ["remove"]):
        raise SystemExit("Use one command: import or remove; no token/password arguments.")
    print("MAKO — локальное агентское подключение, доступ только владельцу/администратору.")
    try:
        with Session(get_engine()) as db:
            org = authorized_organization(db)
            if mode == ["import"]:
                vault = DirectVault(load_vault_key())
                import_token(db, org, vault)
            else:
                remove_token(db, org)
    except (ValueError, DirectVaultError) as exc:
        raise SystemExit(str(exc)) from None


if __name__ == "__main__":
    main()
