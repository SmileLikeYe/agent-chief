#!/usr/bin/env bash
# The whole integration: POST a candidate event, get a Decision back.
# Token comes from ~/.chief/config.toml [ingest].webhook_token
set -euo pipefail

CHIEF_URL="${CHIEF_URL:-http://localhost:8787}"
CHIEF_TOKEN="${CHIEF_TOKEN:-change-me}"

curl -sS -X POST "$CHIEF_URL/v1/events" \
  -H "Authorization: Bearer $CHIEF_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "source": "my-agent",
    "topic": "dev.ci",
    "summary": "CI failed on main: test_auth_flow broken by PR #482",
    "suggested_action": "revert #482 or fix the fixture",
    "evidence": ["https://github.com/acme/repo/actions/runs/9"],
    "claimed_urgency": "high"
  }'
echo
