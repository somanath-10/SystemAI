from __future__ import annotations

import asyncio
import json
import platform

from systemai.config import Settings
from systemai.desktop import DesktopControlService
from systemai.execution import CuaCLIClient, CuaCLIConfig


async def main() -> int:
    settings = Settings()
    client = CuaCLIClient(
        CuaCLIConfig(
            binary=settings.cua_driver_binary,
            socket_path=settings.cua_driver_socket,
            timeout_seconds=settings.cua_timeout_seconds,
        )
    )
    desktop = DesktopControlService(client, session=settings.desktop_session)
    status = await desktop.status()
    print(json.dumps(status.model_dump(mode="json"), indent=2))
    if not status.available:
        print("\nDesktop driver is not ready. Install/start Cua Driver and rerun this command.")
        return 2
    if platform.system() == "Darwin" and status.permissions and not status.permissions.ready:
        print("\nmacOS permissions are incomplete. Accessibility and Screen Recording are both required.")
        return 3

    apps = await desktop.list_apps()
    print(f"\nVisible/running applications: {len(apps)}")
    for app in apps[:20]:
        print(f"- {app.name} pid={app.pid} bundle={app.bundle_id or '-'}")
    if not apps:
        print("No applications were returned; open a GUI application in the same desktop session and retry.")
        return 4
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
