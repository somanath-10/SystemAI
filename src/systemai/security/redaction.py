from __future__ import annotations

import hashlib
from typing import Any

_BINARY_KEYS = {
    "screenshot_png_b64",
    "screenshotPngB64",
    "data_base64",
    "dataBase64",
    "image_base64",
    "imageBase64",
}


def persistence_safe(value: Any, *, max_string_chars: int = 50_000) -> Any:
    """Remove large binary/image payloads before audit or long-term memory persistence.

    Live task state may still contain an image long enough for verification/vision, but
    screenshots are not copied into the hash ledger or episodic trajectory database.
    """
    if isinstance(value, dict):
        out: dict[str, Any] = {}
        for key, item in value.items():
            if key in _BINARY_KEYS and isinstance(item, str):
                out[key] = {
                    "redacted": True,
                    "kind": "base64-binary",
                    "sha256": hashlib.sha256(item.encode("utf-8", errors="ignore")).hexdigest(),
                    "characters": len(item),
                }
            else:
                out[key] = persistence_safe(item, max_string_chars=max_string_chars)
        return out
    if isinstance(value, list):
        return [persistence_safe(item, max_string_chars=max_string_chars) for item in value]
    if isinstance(value, tuple):
        return [persistence_safe(item, max_string_chars=max_string_chars) for item in value]
    if isinstance(value, bytes):
        return {
            "redacted": True,
            "kind": "bytes",
            "sha256": hashlib.sha256(value).hexdigest(),
            "bytes": len(value),
        }
    if isinstance(value, str) and len(value) > max_string_chars:
        return {
            "redacted": True,
            "kind": "oversize-text",
            "sha256": hashlib.sha256(value.encode("utf-8", errors="ignore")).hexdigest(),
            "characters": len(value),
            "prefix": value[:512],
        }
    return value
