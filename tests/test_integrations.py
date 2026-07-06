"""Step 30 acceptance (SPEC v3.1): upstream integration examples.

Both scripts under examples/integrations/ run end-to-end on fixture data and
produce visible Decisions — offline, no daemon, no keys.
"""

import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).parent.parent
INTEGRATIONS = ROOT / "examples" / "integrations"


def run_script(name: str, tmp_path, *args) -> str:
    env = {**os.environ, "CHIEF_HOME": str(tmp_path)}
    proc = subprocess.run(
        [sys.executable, str(INTEGRATIONS / name), *args],
        capture_output=True, text=True, env=env, cwd=ROOT, timeout=120,
    )
    assert proc.returncode == 0, proc.stderr
    return proc.stdout


def test_stock_analysis_bot_runs_end_to_end(tmp_path):
    out = run_script("stock_analysis_bot.py", tmp_path)
    assert "drop" in out  # the daily "no change" reports die
    assert "digest" in out  # real findings survive conservatively
    assert out.count("→") >= 5  # visible per-event decisions
    assert "reason" in out.lower() or "zero-information" in out.lower()


def test_webhook_template_offline_mode(tmp_path):
    out = run_script("webhook_template.py", tmp_path)
    assert "drop" in out and "digest" in out
    assert "Decision" in out or "route" in out


def test_integrations_readme_explains_both_flows():
    text = (INTEGRATIONS / "README.md").read_text(encoding="utf-8")
    assert "stock" in text.lower()
    assert "webhook" in text.lower()
    assert "judgment layer" in text.lower()
