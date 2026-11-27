"""Local-development password hashing and opaque session tokens.

There are no preset passwords, authentication bypass headers, or bearer tokens.
The application must not be exposed to the public Internet at this stage.
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import os
import secrets
from datetime import datetime, timedelta, timezone

SCHEME = "scrypt"
N = 1 << 14
R = 8
P = 1
MAXMEM = 64 * 1024 * 1024
COOKIE_NAME = "mako_session"
SESSION_LIFETIME = timedelta(hours=12)


def _b64(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).decode("ascii").rstrip("=")


def _unb64(value: str) -> bytes:
    return base64.urlsafe_b64decode(value + "=" * (-len(value) % 4))


def hash_password(password: str) -> str:
    """Hash a user-entered password. Never store the plaintext password."""
    if not 12 <= len(password) <= 128:
        raise ValueError("Password must be between 12 and 128 characters")
    salt = os.urandom(16)
    value = hashlib.scrypt(
        password.encode("utf-8"), salt=salt, n=N, r=R, p=P, maxmem=MAXMEM, dklen=32
    )
    return f"{SCHEME}${N}${R}${P}${_b64(salt)}${_b64(value)}"


def verify_password(password: str, stored_hash: str) -> bool:
    """Reject malformed/unsupported hashes without performing unbounded work."""
    try:
        scheme, n_value, r_value, p_value, salt_b64, digest_b64 = stored_hash.split("$")
        if (scheme, n_value, r_value, p_value) != (SCHEME, str(N), str(R), str(P)):
            return False
        salt, expected = _unb64(salt_b64), _unb64(digest_b64)
        if len(salt) != 16 or len(expected) != 32 or len(password) > 128:
            return False
        actual = hashlib.scrypt(
            password.encode("utf-8"), salt=salt, n=N, r=R, p=P, maxmem=MAXMEM, dklen=32
        )
        return hmac.compare_digest(actual, expected)
    except (ValueError, TypeError):
        return False


def new_session_token() -> str:
    return secrets.token_urlsafe(32)


def token_digest(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def session_expires_at() -> datetime:
    return datetime.now(timezone.utc) + SESSION_LIFETIME
