# Release checklist — v0.2.0

## Pre-flight (automated)
- [x] `make release-check` — lint + tests + build + demo runs from the built wheel
- [x] CHANGELOG.md entry for v0.2.0
- [x] Git tag `v0.2.0` → the Release workflow builds, re-verifies, and attaches dist/*
- [x] GitHub releases published for v0.1.0 (retro) and v0.2.0 (latest)

## Publish (needs human credentials)
- [x] Real PyPI: published `agent-chief` 0.3.1 (2026-07-07); verified
      `uvx agent-chief demo` and `uvx agent-chief --version` from the live index
- [x] Restored the PyPI badge in README.md / README.zh-CN.md
- Going forward: publishing is automated via Trusted Publishing
      (`.github/workflows/publish.yml`, see docs/PUBLISHING.md) — tag to release,
      no token needed

---

# Release checklist — v0.1.0 (shipped 2026-07-04)

## Pre-flight (automated)
- [x] `make release-check` — lint + tests + build + demo runs from the built wheel
- [x] `make demo-gif` — README GIF reproduced from source (asciinema + agg)
- [x] Git tag `v0.1.0`

## Publish (needs human credentials)
- [ ] Test PyPI: `uv publish --index testpypi` (token required), then verify
      `uvx --index-url https://test.pypi.org/simple/ agent-chief demo`
- [ ] Real PyPI: `uv publish` (name `agent-chief` confirmed free on 2026-07-04)
- [x] GitHub release on the `v0.1.0` tag (backfilled 2026-07-06 via the notes-sync workflow; the demo GIF ships in the README rather than as a release asset)

## Ecosystem
- [ ] ClawHub submission: `skills/openclaw/` (SKILL.md + hook), positioning line:
      "Chief is the prefrontal cortex; OpenClaw is the limbs and channels."
- [ ] awesome-list PRs: awesome-mcp-servers (chief MCP: propose/feedback/policy/stats),
      awesome-claude-code (dispatch executor), awesome-selfhosted (local-first attention firewall)
- [ ] Hero GIF thread: three events, three fates (#9 CI fix, #16 flight, #1 heartbeat)
- [ ] Deep-dive post 1: the association chain (#5→#19 full trace)
- [ ] Deep-dive post 2: dispatch verification ("done is a claim, not a proof")
- [ ] 2-min video: "the morning briefing" script (SPEC §11)
