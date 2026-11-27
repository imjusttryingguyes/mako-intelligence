"""ONE-TIME setup for the separate local Direct encryption key volume.

Run in VS Code after rebuilding Docker:
    docker compose exec --user root backend python -m mako_intelligence.tools.init_direct_key

Refuses to replace an existing key, because doing so loses the ability to
decrypt stored credentials. NEVER print, export, commit or share the key.
"""
from __future__ import annotations

import grp
import os
import stat

from cryptography.hazmat.primitives.ciphers.aead import AESGCM

from mako_intelligence.integrations.direct_vault import key_path


def main() -> None:
    if os.geteuid() != 0:
        raise SystemExit("Run key initialization with Docker exec --user root")
    folder = key_path().parent
    if not folder.is_dir() or folder.is_symlink():
        raise SystemExit("Direct secret volume is not mounted; aborting.")
    location = key_path()
    if location.exists() or location.is_symlink():
        raise SystemExit("Key already exists. Refusing to replace it.")
    group_id = grp.getgrnam("mako").gr_gid
    key = AESGCM.generate_key(bit_length=256)
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    descriptor = os.open(location, flags, 0o600)
    try:
        with os.fdopen(descriptor, "wb") as output:
            output.write(key)
        os.chown(location, 0, group_id)
        os.chmod(location, stat.S_IRUSR | stat.S_IRGRP)
        os.chown(folder, 0, group_id)
        os.chmod(folder, stat.S_IRWXU | stat.S_IRGRP | stat.S_IXGRP)
    except OSError:
        # Fail closed: no plaintext key is logged; inspect file ownership locally.
        raise SystemExit("Could not secure the local key permissions") from None
    print("Direct encryption key initialized in its separate Docker volume.")
    print("Key not shown; keep the Docker volume and protect workstation backups.")


if __name__ == "__main__":
    main()
