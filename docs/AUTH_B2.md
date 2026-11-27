# Milestone B2.2 — local-only sign-in and project list

This milestone adds a **development-only** sign-in page and authenticated, read-only project list. It is not approved for production or external exposure.

## Security model

- Backend local auth is **disabled by default**. It is enabled explicitly in the local `compose.yaml` with `MAKO_LOCAL_AUTH_ENABLED=1`. Do not deploy with this flag to a publicly reachable server.
- Initial owner and empty demonstration project are created **once** by a Docker terminal command. The password is entered using a hidden terminal prompt, not as an argument, environment variable, source file or chat message.
- Passwords use `hashlib.scrypt` with a random 16-byte salt. No plaintext/reversible passwords are stored.
- Login creates a cryptographically random opaque session token. Only its SHA-256 digest is stored in `auth_sessions`. Sessions expire after 12 hours.
- Browser session cookie uses `HttpOnly`, `SameSite=Strict`, and a host-only path. **Secure=False is for HTTP localhost ONLY**; public HTTPS requires secure cookies and a security review.
- Login/logout require `Origin: http://localhost:3000` and reject absent/foreign origins, reducing cross-site request forgery risk.
- Login never accepts user ID; the server resolves identity from the stored session. Every org/project query is scoped to that verified user and organization.
- Users outside an organization or project get the same 404 response as nonexistent resources.
- The system does **not yet** implement account recovery, user invitations, IP-based throttling, multifactor authentication, security audit logs, or a deployment-ready reverse-proxy/HTTPS setup.

## Local setup (VS Code / PowerShell)

With Docker Desktop running, inside the project folder:

```powershell
git pull
docker compose up --build -d
docker compose exec backend alembic -c /app/alembic.ini upgrade head
docker compose exec backend alembic -c /app/alembic.ini current
docker compose exec backend python -m mako_intelligence.tools.bootstrap_local_owner
```

The Alembic version should be `0002_local_auth (head)`.

At the interactive prompts, enter your desired login email and display name, then a **new unique password of at least 12 characters** twice. The password does not appear on screen. Do not share it in chat or screenshots.

The bootstrap aborts if any organization or user already exists; it never deletes or replaces data.

Open `http://localhost:3000`. Log in with your chosen credentials. You should see the organization `MAKO Intelligence` and the empty `Демо-проект` card. Sign out using **Выйти**.

## Endpoints

- `POST /auth/login`: requires frontend Origin; issues cookie.
- `GET /auth/me`: current authenticated identity.
- `POST /auth/logout`: revokes current token and clears cookie.
- `GET /organizations`: organizations joined through server-side membership.
- `GET /organizations/{organization_id}/projects`: only visible projects.
- `GET /organizations/{organization_id}/projects/{project_id}`: access-controlled detail, 404 on denied/missing.

## Scope boundary before real pilot

Do not enable inbound internet access or use any client data. Before production, we need HTTPS with secure cookies, anti-brute-force protection, invite/verification, admin lifecycle, backup/restore, data residency/privacy review, an audit log and a third-party security review. Local testing is appropriate; customer rollout is not.
