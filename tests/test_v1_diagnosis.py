import json
import sys
from pathlib import Path

from systemai.diagnostics import DeveloperDiagnosisEngineV1


def test_missing_env_stops_without_inventing_secret(tmp_path: Path):
    project = tmp_path / "p"
    (project / ".systemai").mkdir(parents=True)
    (project / ".env.example").write_text("DATABASE_URL=\nSECRET_KEY=\n")
    (project / ".systemai" / "project.json").write_text(json.dumps({"name":"p","runtime":"python","start":[sys.executable,"app.py"],"required_env":["DATABASE_URL","SECRET_KEY"]}))
    report = DeveloperDiagnosisEngineV1().diagnose("t1", project)
    assert report.recommended_actions == []
    assert report.hypotheses[0].code == "missing_environment"
    assert "SECRET_KEY" in report.hypotheses[0].cause
    assert "values" not in report.facts["env"]


def test_manifest_cannot_escape_project_or_probe_remote_url(tmp_path: Path):
    project = tmp_path / "p"
    (project / ".systemai").mkdir(parents=True)
    (project / ".systemai" / "project.json").write_text(
        json.dumps({"name": "p", "runtime": "python", "start": [sys.executable, "app.py"], "cwd": "..", "health_url": "https://example.com/health", "log_files": ["../secret.log"]})
    )
    report = DeveloperDiagnosisEngineV1().diagnose("t1", project)
    assert report.recommended_actions == []
    assert report.hypotheses[0].code == "unsafe_manifest"
    assert "outside project root" in report.hypotheses[0].cause


def test_invalid_manifest_stops_without_raising(tmp_path: Path):
    project = tmp_path / "p"
    (project / ".systemai").mkdir(parents=True)
    (project / ".systemai" / "project.json").write_text("{not valid json")
    report = DeveloperDiagnosisEngineV1().diagnose("t1", project)
    assert report.recommended_actions == []
    assert report.hypotheses[0].code == "invalid_manifest"
    assert "manifest_error" in report.facts
