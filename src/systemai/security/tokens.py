from __future__ import annotations

import base64
import hashlib
import hmac
import json
import secrets
from datetime import datetime, timedelta, timezone
from typing import Any


class CapabilityTokenError(RuntimeError):
    pass


class CapabilityTokenService:
    """Short-lived HMAC capability tokens for privileged/external executors."""

    def __init__(self, secret: bytes | None = None) -> None:
        self._secret = secret or secrets.token_bytes(32)

    def issue(
        self,
        *,
        task_id: str,
        action_id: str,
        capability: str,
        scope: dict[str, Any] | None = None,
        ttl_seconds: int = 60,
    ) -> str:
        now = datetime.now(timezone.utc)
        payload = {
            "task_id": task_id,
            "action_id": action_id,
            "capability": capability,
            "scope": scope or {},
            "iat": int(now.timestamp()),
            "exp": int((now + timedelta(seconds=ttl_seconds)).timestamp()),
            "nonce": secrets.token_hex(8),
        }
        encoded = _b64(json.dumps(payload, separators=(",", ":"), sort_keys=True).encode())
        signature = _b64(hmac.new(self._secret, encoded.encode(), hashlib.sha256).digest())
        return f"{encoded}.{signature}"

    def verify(
        self,
        token: str,
        *,
        task_id: str,
        action_id: str,
        capability: str,
    ) -> dict[str, Any]:
        try:
            encoded, signature = token.split(".", 1)
        except ValueError as exc:
            raise CapabilityTokenError("malformed token") from exc

        expected = _b64(hmac.new(self._secret, encoded.encode(), hashlib.sha256).digest())
        if not hmac.compare_digest(signature, expected):
            raise CapabilityTokenError("invalid signature")

        payload = json.loads(_unb64(encoded))
        now = int(datetime.now(timezone.utc).timestamp())
        if payload["exp"] < now:
            raise CapabilityTokenError("token expired")
        if payload["task_id"] != task_id:
            raise CapabilityTokenError("task mismatch")
        if payload["action_id"] != action_id:
            raise CapabilityTokenError("action mismatch")
        if payload["capability"] != capability:
            raise CapabilityTokenError("capability mismatch")
        return payload


def _b64(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).decode().rstrip("=")


def _unb64(data: str) -> bytes:
    padding = "=" * (-len(data) % 4)
    return base64.urlsafe_b64decode(data + padding)
