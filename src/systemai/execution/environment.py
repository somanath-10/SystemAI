from __future__ import annotations

import os
from typing import Any


_SAFE_ENV_KEYS = {"PATH", "HOME", "TMPDIR", "TEMP", "TMP", "LANG", "LC_ALL", "PYTHONPATH", "VIRTUAL_ENV", "NODE_ENV"}
_SECRET_MARKERS = ("TOKEN", "SECRET", "PASSWORD", "API_KEY", "PRIVATE_KEY")


def clean_environment(extra: dict[str, Any]) -> dict[str, str]:
    env = {key: value for key, value in os.environ.items() if key in _SAFE_ENV_KEYS}
    for key, value in extra.items():
        if not any(marker in str(key).upper() for marker in _SECRET_MARKERS):
            env[str(key)] = str(value)
    return env
