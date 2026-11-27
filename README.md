# MAKO Intelligence — Core 0.1

**Milestones A–B2.4b complete. C1: isolated, read-only Yandex Direct API client (no account connected yet).**

This is a **local-only development scaffold, not a production application**. The local login uses a salted scrypt password hash and revocable database-backed HttpOnly cookie sessions. Organization/project read APIs and project creation use verified sessions and B2.1 tenant access rules. Only organization owners/admins may create projects; POST also checks the request Origin. No real advertising data or paid AI is connected. C1 includes a disabled-by-default provider client and optional interactive local probe; no OAuth token is persisted or uploaded. Do not expose it publicly.

## Requirements
- Git
- Docker Engine + Docker Compose (or eligible Docker Desktop installation)
- Enough memory for local PostgreSQL, FastAPI and Next.js containers

## Launch locally (Windows PowerShell)
```powershell
Copy-Item .env.example .env
docker compose up --build
```

Open `http://localhost:3000`: you should see **API работает**. API: `http://localhost:8000/healthz`; readiness check (includes PostgreSQL): `http://localhost:8000/readyz`. Swagger docs: `http://localhost:8000/docs`.

Run in the terminal if something does not start:
```powershell
docker compose ps
docker compose logs --tail=100 backend
docker compose logs --tail=100 frontend
```

Stop containers: `docker compose down`. **CAUTION:** `docker compose down -v` deletes your local database volume.

The sample password is **only for local development** and MUST be changed before any server deployment. No customer data should ever be placed in this scaffold.

## Database migrations (Milestone B1)
After `git pull`, rebuild and apply the first additive migration, keeping the existing PostgreSQL volume:

```powershell
docker compose up --build -d
docker compose exec backend alembic -c /app/alembic.ini upgrade head
docker compose exec backend alembic -c /app/alembic.ini current
```

See `docs/SCHEMA_B1.md` for the table design and security caveats. **Do not run `docker compose down -v`**: this deletes your local database.

## B2.2 local owner and first login (after pulling changes)

```powershell
git pull
docker compose up --build -d
docker compose exec backend alembic -c /app/alembic.ini upgrade head
docker compose exec backend python -m mako_intelligence.tools.bootstrap_local_owner
```

The bootstrap prompts interactively for an email, display name and password twice (password is not echoed). It refuses if any organization or user already exists; it creates one owner, MAKO organization and an empty demo project. Open `http://localhost:3000` and log in. **Never type the password into a command argument, screenshot, GitHub issue or chat.** See `docs/AUTH_B2.md`.

## B2.3 project creation
After `git pull` and `docker compose up --build -d`, open `http://localhost:3000` and sign in.
Organization owners/admins see a **+ Новый проект** button. Give the new project a title
and a unique, URL-friendly code (Latin letters/numbers/hyphens, 3–80 characters).
The browser suggests a code from the Russian project name. The server validates
both values and enforces uniqueness within each organization.
A new project is an **empty record**; no advertising connection or client data is created.
Project members and outsiders cannot use the creation endpoint.
No migration is necessary for B2.3. Existing demo project and credentials are preserved.

## B2.4a project renaming
After `git pull` and `docker compose up --build -d`, open the dashboard.
Organization owners and admins can choose **Переименовать** on active project
cards. Edit and save the display name; project UUID, URL-friendly code, project
membership and organization stay unchanged. Archived projects are read-only.
The backend requires a valid session and matching frontend Origin on PATCH,
and denies access to normal members and users from different organizations.
This increment adds **no database migration**. Do not use real client data yet.

## B2.4b archive/restore and history
After `git pull`, rebuild, then **apply additive migration 0003**:

```powershell
docker compose up --build -d
docker compose exec backend alembic -c /app/alembic.ini upgrade head
docker compose exec backend alembic -c /app/alembic.ini current
```

Expect `0003_project_events (head)`. Organization owners/admins can archive or
restore projects using a two-step confirmation on each card. Archived projects
stay visible but are read-only; nothing is deleted. An **История** link displays
the last 100 rename/archive/restore actions with actor and timestamp.
History starts **after installing migration 0003**; old renames cannot be
reconstructed retroactively.

The PostgreSQL audit table blocks row UPDATE and DELETE through a trigger.
This is suitable for local development, not a tamper-proof production audit
because a privileged database administrator can change database triggers.
Never use `docker compose down -v` to stop the app. No customer data yet.

## C1 — Yandex Direct read-only API contract

A minimal provider adapter can read campaign IDs/names and list agency client
logins via API `v501` only after the developer's OAuth app is registered and
approved for Direct API access. It has **no HTTP endpoints**, no background
jobs, no token storage and no database migrations. Tests use fake responses
only and do not contact Yandex. See `docs/YANDEX_DIRECT_C1.md`.

Once **you independently obtain approved API access**, a temporary local
read-only probe is available:

```powershell
docker compose exec backend python -m mako_intelligence.tools.yandex_direct_probe
```

The prompt hides the token (never put it in the command line, a chat, GitHub,
a screenshot, the frontend or an environment file). It prints only counts,
not account/client/campaign names. Do not use a live customer account without
authorization. We will design secure persistent OAuth linkage in C2.

## Tests
```bash
python -m pip install -e './backend[dev]'
python -m pytest backend/tests -q
python -m ruff check backend/src backend/tests
```

Frontend without Docker (Node.js 22):
```bash
cd frontend
npm ci
npm run typecheck
npm run build
npm run dev
```

The page displays `API недоступен` when the backend is off. This is expected.

**Reproducibility:** `frontend/package-lock.json` is committed and contains platform-specific optional packages for Linux glibc, Linux musl (Docker Alpine), and Windows. CI and Docker install with `npm ci`. When dependencies change, regenerate the lockfile from a clean installation and verify both CI and the Docker build.

## Architecture
- `frontend/`: Next.js UI and backend status.
- `backend/`: FastAPI liveness, readiness, deterministic metrics, ORM tenant models, Alembic migrations.
- `compose.yaml`: PostgreSQL, backend, frontend; ports exposed **only to localhost**.
- `.github/workflows/ci.yml`: read-only public GitHub Actions, no production secrets.
- `docs/`: roadmap, cost-first decision, product brief.

The full detailed project brief is maintained separately in the original MAKO Intelligence TZ v0.1 document; `docs/PRODUCT_SCOPE.md` records the implementation scope in the repository.

## Security
Do not upload `.env`, tokens, database backups, customer campaign exports, personal data, `.next`, or `node_modules`. The public repository must hold only source code and synthetic test data.
