"""Step 31 acceptance (SPEC v3.1): every README number is reproducible.

`make readme-metrics` regenerates the metrics block; this test is the gate:
the committed README must contain exactly what the script computes today.
"""

import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).parent.parent
README = (ROOT / "README.md").read_text(encoding="utf-8")
MARKER = re.compile(r"<!-- metrics:start -->\n(.*?)<!-- metrics:end -->", re.DOTALL)


def generated_block() -> str:
    proc = subprocess.run(
        [sys.executable, str(ROOT / "scripts" / "readme_metrics.py")],
        capture_output=True, text=True, cwd=ROOT, timeout=120,
    )
    assert proc.returncode == 0, proc.stderr
    return proc.stdout


def test_readme_metrics_block_matches_regeneration():
    m = MARKER.search(README)
    assert m, "README missing <!-- metrics:start/end --> markers"
    assert m.group(1).strip() == generated_block().strip()


def test_metrics_cover_the_five_required_numbers():
    block = generated_block().lower()
    for needle in ("intercept", "interrupt", "llm", "cache", "$"):
        assert needle in block, f"metrics block missing {needle!r}"


def test_makefile_has_readme_metrics_target():
    mk = (ROOT / "Makefile").read_text(encoding="utf-8")
    assert "readme-metrics" in mk


def test_readme_promotes_explainable_judgment_and_new_sections():
    assert "chief trace" in README
    assert "Shadow mode" in README and "Tact Report" in README  # kept
    assert "all clear" in README.lower() and "zero-information" in README.lower()  # kept
    low = README.lower()
    assert "skill" in low and "integrations" in low  # new sections
