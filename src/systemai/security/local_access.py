from __future__ import annotations

import os
import secrets
from pathlib import Path


class RuntimeOwnership:
    """Only the lock holder may initialize or recover this runtime directory."""

    def __init__(self, directory: Path) -> None:
        # shortcut: runtime ownership is POSIX-only; add an OS-backed lock before enabling Windows runtimes.
        if os.name != "posix":
            raise RuntimeError("Runtime ownership currently requires macOS or Linux")
        import fcntl

        self.fd = os.open(directory / "runtime.lock", os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW, 0o600)
        try:
            fcntl.flock(self.fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError as exc:
            os.close(self.fd)
            self.fd = None
            raise RuntimeError("Another SystemAI runtime owns this data directory; use its API or stop it first") from exc

    def close(self) -> None:
        if self.fd is not None:
            os.close(self.fd)
            self.fd = None


def local_api_token(directory: Path, configured: str = "") -> str:
    if configured:
        if len(configured) < 32 or any(not 33 <= ord(char) <= 126 for char in configured):
            raise ValueError("SYSTEMAI_API_TOKEN must contain at least 32 printable non-whitespace ASCII characters")
        return configured
    directory = directory / "keys"
    directory.mkdir(mode=0o700, parents=True, exist_ok=True)
    path = directory / "local-api-token"
    try:
        fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
    except FileExistsError:
        if path.is_symlink() or not path.is_file():
            raise ValueError("Invalid local API access-key file")
        path.chmod(0o600)
        token = path.read_text().strip()
        if len(token) != 64 or any(char not in "0123456789abcdef" for char in token):
            raise ValueError("Invalid local API access-key file")
        return token
    with os.fdopen(fd, "w") as output:
        token = secrets.token_hex(32)
        output.write(token + "\n")
        output.flush()
        os.fsync(output.fileno())
    return token
