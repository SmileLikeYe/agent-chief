"""Release metadata must agree before a tag can publish a wheel."""

import subprocess
import sys
import tomllib
from pathlib import Path

ROOT = Path(__file__).parent.parent
SCRIPT = ROOT / "scripts" / "check_release_version.py"


def project_version() -> str:
    with (ROOT / "pyproject.toml").open("rb") as stream:
        return tomllib.load(stream)["project"]["version"]


def run_guard(expected: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(SCRIPT), expected],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )


def test_release_metadata_matches_project_version():
    result = run_guard(project_version())

    assert result.returncode == 0, result.stderr
    assert f"release metadata ok: {project_version()}" in result.stdout


def test_release_guard_rejects_wrong_tag():
    result = run_guard("9.9.9")

    assert result.returncode != 0
    assert "does not match project version" in result.stderr
