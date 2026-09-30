from __future__ import annotations

import secrets
from time import monotonic


class EphemeralValues:
    """Short-lived, process-only values that never enter task snapshots or events."""

    def __init__(self) -> None:
        # ponytail: values expire after 15 minutes; credential workflows need an OS Secret Broker.
        self._items: dict[str, tuple[str, float]] = {}

    def stash(self, value: str) -> str:
        if len(value) > 10_000:
            raise ValueError("input exceeds 10,000 characters")
        self._items = {key: item for key, item in self._items.items() if item[1] > monotonic()}
        reference = secrets.token_urlsafe(24)
        self._items[reference] = (value, monotonic() + 900)
        return reference

    def consume(self, reference: str) -> str:
        saved = self._items.pop(reference, None)
        if saved is None or saved[1] <= monotonic():
            raise ValueError("input expired or was lost after restart; create a new task")
        return saved[0]

    def forget(self, reference: str) -> None:
        self._items.pop(reference, None)

    def clear(self) -> None:
        self._items.clear()
