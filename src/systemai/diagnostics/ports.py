from __future__ import annotations

from types import SimpleNamespace
from typing import Any

import psutil


def listening_connections(port: int | None = None) -> list[Any]:
    """Return visible listening sockets without letting one protected process abort diagnosis."""
    try:
        connections = psutil.net_connections(kind="inet")
    except (psutil.AccessDenied, OSError):
        connections = []
        for process in psutil.process_iter(["pid"]):
            try:
                connections.extend(
                    connection
                    if hasattr(connection, "pid")
                    else SimpleNamespace(
                        family=getattr(connection, "family", None),
                        type=getattr(connection, "type", None),
                        laddr=connection.laddr,
                        raddr=getattr(connection, "raddr", None),
                        status=connection.status,
                        pid=process.pid,
                    )
                    for connection in process.net_connections(kind="inet")
                )
            except (psutil.AccessDenied, psutil.NoSuchProcess, OSError):
                continue
    return [
        connection
        for connection in connections
        if connection.status == psutil.CONN_LISTEN
        and connection.laddr
        and (port is None or connection.laddr.port == port)
    ]


def port_is_listening(port: int) -> bool:
    return bool(listening_connections(port))
