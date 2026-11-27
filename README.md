# MAKO Intelligence — Core 0.1

**Milestone A: free, local-first development foundation.**

This is a **technical scaffold, not a production application**. There is no login, multi-tenant authorization, Yandex OAuth, real advertising data, or paid AI integration yet. Do not deploy publicly.

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
- `backend/`: FastAPI liveness, readiness and deterministic metric calculations.
- `compose.yaml`: PostgreSQL, backend, frontend; ports exposed **only to localhost**.
- `.github/workflows/ci.yml`: read-only public GitHub Actions, no production secrets.
- `docs/`: roadmap, cost-first decision, product brief.

The full detailed project brief is maintained separately in the original MAKO Intelligence TZ v0.1 document; `docs/PRODUCT_SCOPE.md` records the implementation scope in the repository.

## Security
Do not upload `.env`, tokens, database backups, customer campaign exports, personal data, `.next`, or `node_modules`. The public repository must hold only source code and synthetic test data.
