from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
from pathlib import Path

from systemai.runtime import VERSION, build_runtime


def _parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="systemai", description="SystemAI — trusted local developer diagnosis runtime")
    p.add_argument("--data-dir", default=os.environ.get("SYSTEMAI_DATA_DIR", str(Path.home() / ".systemai" / "runtime")))
    sub = p.add_subparsers(dest="cmd", required=True)
    sub.add_parser("version")
    d = sub.add_parser("diagnose", help="Diagnose and repair a declared development project")
    d.add_argument("project", type=Path)
    d.add_argument("--goal", default="Find why this project is not running and fix it.")
    d.add_argument("--autonomy", choices=["observe", "assist", "standard_auto"], default="standard_auto")
    d.add_argument("--non-interactive", action="store_true")
    e = sub.add_parser("events", help="Show recent durable events")
    e.add_argument("--task-id")
    e.add_argument("--limit", type=int, default=200)
    sub.add_parser("doctor", help="Check local prerequisites")
    return p


async def _diagnose(args) -> int:
    runtime = build_runtime(data_dir=Path(args.data_dir), autonomy_mode=args.autonomy)
    session = await runtime.create_developer_task(args.goal, args.project)
    while session.state.value == "waiting_for_approval":
        action_id, approval_id = next(iter(session.pending_approvals.items()))
        record = runtime.security_kernel.approvals.get(approval_id)
        print("\nAPPROVAL REQUIRED\n" + "=" * 72)
        print(record["canonical_summary"])
        print("=" * 72)
        if args.non_interactive or not sys.stdin.isatty():
            print("Task paused. Re-run interactively or approve through the API/Command Center.")
            print(json.dumps(session.snapshot(), indent=2, default=str))
            return 2
        answer = input("Approve this exact action? [y/N] ").strip().lower()
        runtime.approve(session.task_id, action_id, approved=answer in {"y", "yes"}, reason="CLI user decision")
        if answer not in {"y", "yes"}:
            break
        session = await runtime.run(session.task_id)
    print(json.dumps(session.snapshot(), indent=2, default=str))
    return 0 if session.state.value == "completed" else 1


def _doctor(data_dir: Path) -> int:
    import importlib.util
    import shutil
    checks = {
        "python": sys.version.split()[0],
        "git": shutil.which("git"),
        "ss": shutil.which("ss"),
        "docker": shutil.which("docker"),
        "bwrap": shutil.which("bwrap"),
        "cryptography": bool(importlib.util.find_spec("cryptography")),
        "psutil": bool(importlib.util.find_spec("psutil")),
        "httpx": bool(importlib.util.find_spec("httpx")),
        "data_dir": str(data_dir),
    }
    print(json.dumps(checks, indent=2))
    return 0


def main() -> None:
    args = _parser().parse_args()
    data_dir = Path(args.data_dir).expanduser()
    if args.cmd == "version":
        print(VERSION)
        return
    if args.cmd == "doctor":
        raise SystemExit(_doctor(data_dir))
    if args.cmd == "diagnose":
        raise SystemExit(asyncio.run(_diagnose(args)))
    if args.cmd == "events":
        runtime = build_runtime(data_dir=data_dir)
        print(json.dumps(runtime.store.list_events(task_id=args.task_id, limit=args.limit), indent=2, default=str))
        return


if __name__ == "__main__":
    main()
