from __future__ import annotations

import json
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).parents[1]
checks = {
    "python": sys.version.split()[0],
    "git": shutil.which("git"),
    "node": shutil.which("node"),
    "npm": shutil.which("npm"),
    "cargo": shutil.which("cargo"),
    "docker": shutil.which("docker"),
    "bwrap": shutil.which("bwrap"),
    "master_blueprint": (ROOT / "docs/source/SystemAI_MASTER_BLUEPRINT_UPDATED.md").exists(),
    "eval_catalog": (ROOT / "evals/systemai/catalog.json").exists(),
    "rust_kernel": (ROOT / "native/security-kernel/Cargo.toml").exists(),
}
print(json.dumps(checks, indent=2))
