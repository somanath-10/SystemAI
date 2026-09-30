from __future__ import annotations

import base64
import hashlib
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any
from uuid import uuid4

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey, Ed25519PublicKey

from systemai.contracts.models import ActionIntent, CapabilityTokenClaims


def _b64url(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode("ascii")


def _unb64url(data: str) -> bytes:
    return base64.urlsafe_b64decode(data + "=" * (-len(data) % 4))


def _canonical_json(value: Any) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), default=str).encode("utf-8")


def hash_payload(value: Any) -> str:
    return hashlib.sha256(_canonical_json(value)).hexdigest()


def action_hash(action: ActionIntent) -> str:
    return hash_payload(action.model_dump(mode="json", exclude={"created_at"}))


class CapabilitySigner:
    """Ed25519 capability signer used by the Python dev kernel.

    Production architecture moves this private key into the Rust Security Kernel.
    Executors receive only the public key.
    """

    def __init__(self, private_key: Ed25519PrivateKey, *, key_id: str = "local-ed25519") -> None:
        self._private = private_key
        self.key_id = key_id

    @classmethod
    def generate(cls, *, key_id: str = "local-ed25519") -> "CapabilitySigner":
        return cls(Ed25519PrivateKey.generate(), key_id=key_id)

    @classmethod
    def load_or_create(cls, path: Path, *, key_id: str = "local-ed25519") -> "CapabilitySigner":
        path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        path.parent.chmod(0o700)
        if path.exists():
            try:
                path.chmod(0o600)
            except OSError:
                pass
            private = serialization.load_pem_private_key(path.read_bytes(), password=None)
            if not isinstance(private, Ed25519PrivateKey):
                raise TypeError("capability signing key is not Ed25519")
            return cls(private, key_id=key_id)
        signer = cls.generate(key_id=key_id)
        path.write_bytes(
            signer._private.private_bytes(
                encoding=serialization.Encoding.PEM,
                format=serialization.PrivateFormat.PKCS8,
                encryption_algorithm=serialization.NoEncryption(),
            )
        )
        try:
            path.chmod(0o600)
        except OSError:
            pass
        return signer

    def public_key_pem(self) -> bytes:
        return self._private.public_key().public_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PublicFormat.SubjectPublicKeyInfo,
        )

    def issue(
        self,
        *,
        action: ActionIntent,
        session_id: str,
        executor_id: str,
        device_id: str = "local",
        audience: str = "systemai-executor",
        approval_id: str | None = None,
        ttl_seconds: int = 60,
        provenance_constraints: list[str] | None = None,
    ) -> tuple[str, CapabilityTokenClaims]:
        now = datetime.now(timezone.utc)
        claims = CapabilityTokenClaims(
            key_id=self.key_id,
            audience=audience,
            executor_id=executor_id,
            device_id=device_id,
            session_id=session_id,
            task_id=action.task_id,
            node_id=action.node_id,
            action_id=action.action_id,
            action_hash=action_hash(action),
            capability_name=action.capability,
            resource_scope=action.resource_scope,
            parameter_hash=hash_payload(action.parameters),
            approval_id=approval_id,
            provenance_constraints=provenance_constraints or [],
            issued_at=now,
            expires_at=now + timedelta(seconds=ttl_seconds),
            nonce=uuid4().hex,
            max_uses=1,
        )
        payload = _canonical_json(claims.model_dump(mode="json"))
        signature = self._private.sign(payload)
        token = f"cap1.{_b64url(payload)}.{_b64url(signature)}"
        return token, claims


class CapabilityVerifier:
    def __init__(
        self,
        public_key: Ed25519PublicKey,
        *,
        expected_audience: str = "systemai-executor",
        executor_id: str | None = None,
        device_id: str | None = None,
    ) -> None:
        self._public = public_key
        self.expected_audience = expected_audience
        self.executor_id = executor_id
        self.device_id = device_id
        self._used_nonces: set[str] = set()

    @classmethod
    def from_pem(cls, data: bytes, **kwargs: Any) -> "CapabilityVerifier":
        key = serialization.load_pem_public_key(data)
        if not isinstance(key, Ed25519PublicKey):
            raise TypeError("capability verification key is not Ed25519")
        return cls(key, **kwargs)

    def verify(self, token: str, *, action: ActionIntent, consume: bool = True) -> CapabilityTokenClaims:
        try:
            prefix, payload_b64, signature_b64 = token.split(".", 2)
        except ValueError as exc:
            raise ValueError("invalid capability token format") from exc
        if prefix != "cap1":
            raise ValueError("unsupported capability token version")
        payload = _unb64url(payload_b64)
        signature = _unb64url(signature_b64)
        self._public.verify(signature, payload)
        claims = CapabilityTokenClaims.model_validate(json.loads(payload))
        now = datetime.now(timezone.utc)
        if claims.expires_at <= now:
            raise ValueError("capability token expired")
        if claims.audience != self.expected_audience:
            raise ValueError("capability token audience mismatch")
        if self.executor_id and claims.executor_id != self.executor_id:
            raise ValueError("capability token executor mismatch")
        if self.device_id and claims.device_id != self.device_id:
            raise ValueError("capability token device mismatch")
        if claims.nonce in self._used_nonces:
            raise ValueError("capability token replay detected")
        if claims.action_id != action.action_id or claims.action_hash != action_hash(action):
            raise ValueError("capability token does not authorize this action")
        if claims.capability_name != action.capability:
            raise ValueError("capability token capability mismatch")
        if claims.parameter_hash != hash_payload(action.parameters):
            raise ValueError("capability token parameters mismatch")
        if consume:
            self._used_nonces.add(claims.nonce)
        return claims
