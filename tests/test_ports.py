from types import SimpleNamespace

import psutil

from systemai.diagnostics import ports


def test_port_inspection_skips_protected_processes(monkeypatch):
    connection = SimpleNamespace(status=psutil.CONN_LISTEN, laddr=SimpleNamespace(port=43210))

    def blocked(*args, **kwargs):
        raise psutil.AccessDenied()

    class VisibleProcess:
        pid = 987

        def net_connections(self, kind):
            return [connection]

    monkeypatch.setattr(ports.psutil, "net_connections", blocked)
    monkeypatch.setattr(ports.psutil, "process_iter", lambda attrs: [VisibleProcess()])
    listeners = ports.listening_connections(43210)
    assert listeners[0].pid == 987
    assert listeners[0].laddr.port == 43210
