"""Local web console assets (SPEC v3.2 Step 33). Served by ingest/http.py on
127.0.0.1 only — single user, token-gated APIs, zero build toolchain."""

from pathlib import Path

CONSOLE_HTML_PATH = Path(__file__).parent / "console.html"
