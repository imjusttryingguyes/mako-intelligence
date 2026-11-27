# MAKO Intelligence — Core 0.1

**Milestone A / B1 / B2.1 complete. B2.2: local-only login and protected project list.**

This is a **local-only development scaffold, not a production application**. The local login uses a salted scrypt password hash and revocable database-backed HttpOnly cookie sessions. Read-only organization and project APIs use verified sessions and the B2.1 tenant access rules. No real advertising data, Yandex OAuth or paid AI is connected. Do not expose it publicly.

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
