"""Local-only session authentication.

Mutating requests require the exact configured frontend Origin for CSRF
protection. Sessions live in PostgreSQL, not in browser-local storage.
"""
from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from pydantic import BaseModel, Field
from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from mako_intelligence.core.auth import (
    COOKIE_NAME,
    SESSION_LIFETIME,
    new_session_token,
    session_expires_at,
    token_digest,
    verify_password,
)
from mako_intelligence.core.config import frontend_origin, local_auth_enabled
from mako_intelligence.db.models import AuthSession, LocalCredential, User
from mako_intelligence.db.session import get_db

router = APIRouter(tags=["local-auth"])


class LoginInput(BaseModel):
    email: str = Field(min_length=3, max_length=320)
    password: str = Field(min_length=1, max_length=128)


class UserView(BaseModel):
    id: str
    email: str
    display_name: str


def _check_local_auth() -> None:
    if not local_auth_enabled():
        raise HTTPException(status_code=503, detail="local authentication disabled")


def _require_origin(request: Request) -> None:
    """Reject missing/foreign Origin on every state-changing browser request."""
    if request.headers.get("origin") != frontend_origin():
        raise HTTPException(status_code=403, detail="invalid request origin")


def _user_view(user: User) -> UserView:
    return UserView(id=str(user.id), email=user.email, display_name=user.display_name)


def authenticated_user(request: Request, db: Session = Depends(get_db)) -> User:
    """Resolve identity only from a valid random session cookie (never user input)."""
    _check_local_auth()
    token = request.cookies.get(COOKIE_NAME)
    if not token or len(token) > 256:
        raise HTTPException(status_code=401, detail="not authenticated")
    record = db.get(AuthSession, token_digest(token))
    if record is None or record.expires_at <= datetime.now(timezone.utc):
        raise HTTPException(status_code=401, detail="not authenticated")
    user = db.get(User, record.user_id)
    if user is None:
        raise HTTPException(status_code=401, detail="not authenticated")
    return user


@router.post("/auth/login", response_model=UserView)
def login(
    payload: LoginInput,
    request: Request,
    response: Response,
    db: Session = Depends(get_db),
) -> UserView:
    _check_local_auth()
    _require_origin(request)
    email = payload.email.strip().casefold()
    user = db.scalar(select(User).where(func.lower(User.email) == email))
    password_record = db.get(LocalCredential, user.id) if user else None
    if not password_record or not verify_password(payload.password, password_record.password_hash):
        # Never disclose whether the address or the password was wrong.
        raise HTTPException(status_code=401, detail="invalid email or password")

    token = new_session_token()
    db.execute(
        delete(AuthSession)
        .where(AuthSession.user_id == user.id, AuthSession.expires_at < datetime.now(timezone.utc))
    )
    db.add(AuthSession(
        token_digest=token_digest(token), user_id=user.id, expires_at=session_expires_at(),
    ))
    db.commit()
    response.set_cookie(
        key=COOKIE_NAME,
        value=token,
        httponly=True,
        secure=False,  # LOCALHOST HTTP ONLY; must become True before HTTPS deployment.
        samesite="strict",
        path="/",
        max_age=int(SESSION_LIFETIME.total_seconds()),
    )
    return _user_view(user)


@router.get("/auth/me", response_model=UserView)
def me(user: User = Depends(authenticated_user)) -> UserView:
    return _user_view(user)


@router.post("/auth/logout", status_code=204)
def logout(
    request: Request,
    response: Response,
    db: Session = Depends(get_db),
) -> None:
    _check_local_auth()
    _require_origin(request)
    token = request.cookies.get(COOKIE_NAME)
    if token and len(token) <= 256:
        db.execute(delete(AuthSession).where(AuthSession.token_digest == token_digest(token)))
        db.commit()
    response.delete_cookie(COOKIE_NAME, path="/", samesite="strict")
