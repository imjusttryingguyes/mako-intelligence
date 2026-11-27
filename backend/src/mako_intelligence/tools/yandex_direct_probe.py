"""One-time local, read-only Yandex Direct connection check.

Requires an API-approved OAuth app and account permissions. Token entry can
be visible ONLY by explicit operator choice; hidden is the default.
No token is persisted, logged or used in shell command arguments.
"""
from __future__ import annotations

import getpass

from mako_intelligence.integrations.yandex_direct import DirectReadClient, DirectReadError


def prompt_for_token() -> str:
    """Get token interactively with clear feedback, without persisting it.

    The visible mode is for a private, local terminal only: entering a token
    visibly exposes it in terminal scrollback and any screenshots/recordings.
    """
    print("Ввод OAuth-токена: 1 — показать ввод, 2 — скрыть ввод [2].")
    choice = input("Выбери 1 или 2 (Enter = 2): ").strip() or "2"
    if choice == "1":
        print("ВНИМАНИЕ: токен будет виден в терминале.")
        print("Не делай скриншоты, не записывай терминал и закрой его после проверки.")
        token = input("OAuth-токен (ВИДЕН): ").strip()
    elif choice == "2":
        print("При вставке токена символы НЕ показываются. Это нормально.")
        token = getpass.getpass("OAuth-токен (скрыт): ").strip()
    else:
        raise ValueError("Выбери режим ввода 1 или 2.")

    if not token:
        raise ValueError("Токен пустой: скопируй его заново и повтори проверку.")
    print(f"Токен получен: {len(token)} символов. Проверяем доступ к Директу...")
    return token


def main() -> None:
    print("MAKO Intelligence — локальная проверка чтения Яндекс Директа")
    print("Только чтение. Токен не будет сохранён в базе, .env или истории PowerShell.")
    mode = input("Режим: 1 — рекламодатель, 2 — агентство: ").strip()
    if mode not in ("1", "2"):
        raise SystemExit("Нужно выбрать 1 или 2.")
    client_login: str | None = None
    if mode == "2":
        client_login = input("Логин клиента в Директе: ").strip()
        if not client_login:
            raise SystemExit("Укажи логин клиента агентства.")

    token = ""
    try:
        token = prompt_for_token()
        with DirectReadClient(token) as direct:
            if mode == "2":
                print("Шаг 1/2: AgencyClients.get — читаем список клиентов агентства...")
                agency_clients = direct.get_agency_clients()
                print(f"Доступных клиентов агентства получено: {len(agency_clients)}")
            print("Шаг 2/2: Campaigns.get — читаем кампании...")
            campaigns = direct.get_campaigns(client_login=client_login)
            print(f"Успешное чтение: кампаний получено: {len(campaigns)}")
    except (ValueError, DirectReadError) as exc:
        print(f"Подключение не подтверждено: {exc}")
        if isinstance(exc, DirectReadError) and exc.error_code == 58:
            print("Ошибка 58 — незавершённая регистрация OAuth-приложения для Direct API.")
            print(
                "Если заявка одобрена, сравни Client ID одобренной заявки "
                "с Client ID приложения, ДЛЯ КОТОРОГО получен этот токен."
            )
            print("Частая причина: токен получен для другого OAuth-приложения.")
        elif isinstance(exc, DirectReadError) and exc.error_code == 53:
            print("Ошибка 53 — OAuth-токен недействителен. Проверь его срок и отзыв.")
        raise SystemExit(1) from None
    finally:
        token = ""  # Best effort: Python cannot guarantee secure memory erasure.


if __name__ == "__main__":
    main()
