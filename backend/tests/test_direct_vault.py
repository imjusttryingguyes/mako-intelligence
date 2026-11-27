"""Offline cryptography tests. All credentials and keys are synthetic."""
from __future__ import annotations

import os
import uuid

import pytest
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

from mako_intelligence.integrations.direct_vault import (
    DirectVault,
    DirectVaultError,
    load_vault_key,
)


def test_round_trip_preserves_token_only_for_correct_organization() -> None:
    vault = DirectVault(AESGCM.generate_key(bit_length=256))
    org = uuid.uuid4()
    token = "FAKE-AGENCY-TOKEN-NOT-REAL-123456"
    first = vault.seal(token, org)
    second = vault.seal(token, org)
    assert first != second  # Random nonce on every operation.
    assert token.encode("utf-8") not in first
    assert vault.open(first, org) == token
    with pytest.raises(DirectVaultError, match="cannot be decrypted"):
        vault.open(first, uuid.uuid4())


def test_ciphertext_tamper_and_wrong_key_are_rejected_without_leak() -> None:
    org = uuid.uuid4()
    token = "FAKE-AGENCY-TOKEN-NOT-REAL"
    blob = DirectVault(os.urandom(32)).seal(token, org)
    tampered = blob[:-1] + bytes([blob[-1] ^ 1])
    for candidate in (tampered, b"\x02" + blob[1:], b"\x01", b""):
        with pytest.raises(DirectVaultError) as failure:
            DirectVault(os.urandom(32)).open(candidate, org)
        assert token not in str(failure.value)
    with pytest.raises(DirectVaultError):
        DirectVault(os.urandom(32)).open(blob, org)


def test_invalid_token_or_aes_key_is_refused() -> None:
    with pytest.raises(DirectVaultError):
        DirectVault(b"short")
    vault = DirectVault(os.urandom(32))
    with pytest.raises(DirectVaultError):
        vault.seal("x\nHeader: evil", uuid.uuid4())
    with pytest.raises(DirectVaultError):
        vault.seal("", uuid.uuid4())


def test_load_key_checks_file_mode_length_and_symlinks(tmp_path) -> None:
    key_path = tmp_path / "key.bin"
    key = AESGCM.generate_key(bit_length=256)
    with pytest.raises(DirectVaultError, match="unavailable"):
        load_vault_key(key_path)
    key_path.write_bytes(key)
    key_path.chmod(0o600)
    assert load_vault_key(key_path) == key
    key_path.chmod(0o644)
    with pytest.raises(DirectVaultError, match="permissions"):
        load_vault_key(key_path)
    key_path.chmod(0o600)
    key_path.write_bytes(b"x")
    with pytest.raises(DirectVaultError, match="invalid"):
        load_vault_key(key_path)
    key_path.write_bytes(key)
    shortcut = tmp_path / "shortcut.bin"
    shortcut.symlink_to(key_path)
    with pytest.raises(DirectVaultError, match="invalid"):
        load_vault_key(shortcut)
