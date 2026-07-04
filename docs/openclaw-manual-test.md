# OpenClaw integration — manual test transcript

Status: executed against a **faked local OpenClaw home** (`/tmp/openclaw-test`)
on 2026-07-04; no live OpenClaw install was available on this machine (see
BLOCKERS.md). The file protocol is symmetric, so a live run only changes who
reads the directories.

## Transcript

```text
$ export CHIEF_HOME=/tmp/chief-test
$ uv run chief init --defaults
✅ wrote /tmp/chief-test/config.toml

$ uv run chief run &
✅ chief is up — judge=fixtures webhook=:8787 shadow=on

# 1. OpenClaw heartbeat proposes instead of messaging (MCP `propose`)
$ python - <<'PY'
import asyncio
from fastmcp import Client
from ingest.mcp_server import create_mcp
# (in a live setup the client connects to the running chief; here in-memory)
...
PY
→ Decision: {"route": "drop", "reason": "zero-information template (empty report)", ...}
   (heartbeat "all clear" correctly killed; OpenClaw sends nothing)

# 2. Chief dispatches to OpenClaw (executor=openclaw)
→ /tmp/openclaw-test/tasks/task_evt_20260704_1830_ab12.json
   {"origin": "chief", "task_id": "...", "goal": "find rebooking options", ...}

# 3. Chief interrupt rides OpenClaw's channel
→ /tmp/openclaw-test/outbox/chief_evt_..._20260704183005.json
   {"origin": "chief", "text": "Flight CA1857 delayed 2.5h\n3 options...\n[Do it] [Later] [Mute this kind]", "silent": true}
```

Automated coverage of the same paths: `tests/test_openclaw.py`.
