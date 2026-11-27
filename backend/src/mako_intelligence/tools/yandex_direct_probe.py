"""One-time local, read-only Yandex Direct connection check.

Requires a Yandex Direct API-approved OAuth application and authorized user.
The token is entered in a hidden terminal prompt and is never persisted.
No credentials, account names or campaign names are printed.
"""
from __future__ import annotations

import getpass

from mako_intelligence.integrations.yandex_direct import DirectReadClient, DirectReadError


def main() -> None:
    print("MAKO Intelligence — локальная проверка чтения Яндекс Директа")
    print("Только чтение. Токен не будет сохранён и не появится в истории PowerShell.")
    mode = input("Режим: 1 — рекламодатель, 2 — агентство: ").strip()
    if mode not in ("1", "2"):
        raise SystemExit("Нужно выбрать 1 или 2.")
    client_login: str | None = None
    if mode == "2":
        client_login = input("Логин клиента в Директе: ").strip()
        if not client_login:
            raise SystemExit("Укажи логин клиента агентства.")
    token = getpass.getpass("OAuth-токен (ввод скрыт): ").strip()
    try:
        with DirectReadClient(token) as direct:
            if mode == "2":
                # This request is read-only and uses the agency representative token.
                agency_clients = direct.get_agency_clients()
                print(f"Доступных клиентов агентства получено: {len(agency_clients)}")
            campaigns = direct.get_campaigns(client_login=client_login)
            print(f"Успешное чтение: кампаний получено: {len(campaigns)}")
    except (ValueError, DirectReadError) as exc:
        print(f"Подключение не подтверждено: {exc}")
        raise SystemExit(1) from None
    finally:
        token = ""  # best-effort; Python cannot guarantee secure memory erasure.


if __name__ == "__main__":
    main()
