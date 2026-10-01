from pathlib import Path

import pytest

from systemai.config import Settings
from systemai.runtime import build_runtime


@pytest.mark.asyncio
async def test_process_monitor_has_a_clean_runtime_lifecycle(tmp_path: Path) -> None:
    runtime = build_runtime(
        data_dir=tmp_path,
        settings=Settings(_env_file=None, enable_process_monitor=True, process_monitor_interval_seconds=60),
    )
    assert runtime.monitoring_status() == {"configured": True, "running": False}
    await runtime.start_monitoring()
    assert runtime.monitoring_status()["running"] is True
    await runtime.stop_monitoring()
    assert runtime.monitoring_status()["running"] is False
