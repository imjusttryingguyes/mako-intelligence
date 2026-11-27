"""Local-only AES-256-GCM encryption of agency OAuth tokens.

The 32-byte key lives in a separate Docker volume readable only by the
backend's group. PostgreSQL stores ciphertext, NEVER the key or plaintext.
This does not make a workstation with Docker admin access a hardened KMS.
"""
from __future__ import annotations

import os
import stat
import uuid
from pathlib import Path

from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

VERSION = b"\x01"
KEY_SIZE = 32
NONCE_SIZE = 12
DEFAULT_KEY_PATH = "/run/mako-direct-keys/key.bin"


class DirectVaultError(Exception):
    """Sanitized vault error; never echo ciphertext, key, or OAuth token."""


def key_path() -> Path:
    return Path(os.getenv("MAKO_DIRECT_KEY_PATH", DEFAULT_KEY_PATH))


def load_vault_key(path: Path | None = None) -> bytes:
    location = path or key_path()
    try:
        metadata = location.lstat()
        if not stat.S_ISREG(metadata.st_mode) or metadata.st_size != KEY_SIZE:
            raise DirectVaultError("Direct encryption key file is invalid")
        if metadata.st_mode & 0o007:
            raise DirectVaultError("Direct encryption key permissions are too broad")
        with location.open("rb") as file:
            key = file.read()
        if len(key) != KEY_SIZE:
            raise DirectVaultError("Direct encryption key has wrong length")
        return key
    except (OSError, ValueError):
        raise DirectVaultError("Direct encryption key unavailable; initialize local key") from None


class DirectVault:
    def __init__(self, key: bytes):
        if len(key) != KEY_SIZE:
            raise DirectVaultError("Direct encryption key has wrong length")
        self._aead = AESGCM(key)

    @staticmethod
    def _associated_data(org_id: uuid.UUID) -> bytes:
        return b"mako-direct-vault-v1:" + org_id.bytes

    def seal(self, token: str, org_id: uuid.UUID) -> bytes:
        if not token or any(ord(c) < 32 or ord(c) == 127 for c in token):
            raise DirectVaultError("Invalid OAuth credential")
        nonce = os.urandom(NONCE_SIZE)
        ciphertext = self._aead.encrypt(
            nonce, token.encode("utf-8"), self._associated_data(org_id)
        )
        return VERSION + nonce + ciphertext

    def open(self, blob: bytes, org_id: uuid.UUID) -> str:
        if not blob or not blob.startswith(VERSION) or len(blob) < 30:
            raise DirectVaultError("Direct credential format invalid")
        try:
            plaintext = self._aead.decrypt(
                blob[1:1 + NONCE_SIZE], blob[1 + NONCE_SIZE:],
                self._associated_data(org_id),
            )
            return plaintext.decode("utf-8")
        except (InvalidTag, ValueError, UnicodeDecodeError):
            raise DirectVaultError("Direct credential cannot be decrypted") from None
