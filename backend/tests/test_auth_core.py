"""Unit checks for password storage and session token generation."""
from mako_intelligence.core.auth import (
    hash_password,
    new_session_token,
    token_digest,
    verify_password,
)


def test_password_hash_is_salted_and_not_plaintext() -> None:
    password = "a-distinct-local-secret-2026"
    first = hash_password(password)
    second = hash_password(password)
    assert first != second
    assert password not in first
    assert verify_password(password, first)
    assert verify_password(password, second)
    assert not verify_password("wrong-secret", first)


def test_corrupted_or_unknown_password_hash_is_rejected() -> None:
    assert not verify_password("irrelevant-password", "not-a-hash")
    assert not verify_password("irrelevant-password", "scrypt$999999999$8$1$AA$BB")
    assert not verify_password("irrelevant-password", "")


def test_bootstrap_password_rules() -> None:
    try:
        hash_password("short")
    except ValueError:
        pass
    else:
        raise AssertionError("Password shorter than 12 characters must be rejected")


def test_opaque_session_token_has_unpredictable_value_and_digest() -> None:
    first, second = new_session_token(), new_session_token()
    assert len(first) >= 40
    assert first != second
    assert token_digest(first) != token_digest(second)
    assert len(token_digest(first)) == 64
    assert first not in token_digest(first)
