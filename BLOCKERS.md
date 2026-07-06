# Blockers & Mocked Steps

Log of steps that needed human-only resources; implemented against mocks/fixtures per goal rule 3.

- Step 8: no live LLM API key (DeepSeek/Anthropic/OpenAI) and no local Ollama on this machine. All four adapters implemented and exercised against recorded HTTP cassettes (httpx.MockTransport); the ≥20/24 demo-agreement test uses cassettes synthesized from the demo fixture's judge blocks, so it validates the wire format + parsing + pipeline, not live model quality. To validate live: `chief init`, pick a backend, rerun tests with a key.
- Step 9: sentence-transformers/torch cannot be installed on this machine — disk has <1GB free and CPU torch alone needs ~2GB. The `embeddings` extra + SentenceTransformerEmbedder wiring is implemented and the fallback path is tested; all similarity tests run on the deterministic HashEmbedder. To validate the real model: free ~3GB, `uv sync --extra embeddings`, rerun pytest.
- Step 10: headless dev machine has no notification daemon; DesktopChannel's plyer path is unit-tested with an injected notify_fn and the real path was smoke-tested to degrade gracefully to terminal.
- Step 11: no Telegram bot token / live chat available. Channel implemented against the Bot HTTP API and integration-tested with an httpx test double (sendMessage payloads, silent flag, inline buttons, callback→feedback rows, mute→POLICY.md). To validate live: create a bot via @BotFather, set [delivery] telegram_token/chat_id, run `chief run`.
- Step 17: acceptance says "with real embeddings" — blocked by the same disk constraint as Step 9 (torch will not fit). The #5→#19 chain is verified with the deterministic HashEmbedder through MemoryStore/batch_associate; swap in the real model via config once the embeddings extra is installable.
- Step 20: fresh-machine <10min manual check — verified the local path on this machine: `uv tool install`/`uvx` → `chief init --defaults` (~5s) → `chief run` up with webhook answering in <1 min. A truly fresh machine with a live LLM key could not be exercised tonight (no spare machine/key); the wizard, config, service unit, and run wiring are all covered by tests.
- Step 22: no local OpenClaw install available. Integration is file-protocol based (tasks/ inbox, outbox/ pickup) and fully covered by tests against a faked OpenClaw home; the manual transcript in docs/openclaw-manual-test.md documents the faked run and what a live run would change.
- Step 23: "clean machine" quickstart verified on this machine via isolated uvx (1.8s to demo end, well under 60s); a literally separate machine wasn't available tonight.
- Step 24: publishing to (test) PyPI needs an account token only a human can provide. Everything short of upload is done and verified: `make release-check` runs the demo from the built wheel via isolated uvx (the exact `uvx agent-chief demo` code path), the GIF is reproducible via `make demo-gif`, and v0.1.0 is tagged. To finish: `uv publish --index testpypi` with a token, then re-verify.

## Step 25/27 · Real-backend eval + prompt compare (v3.1)
- Status: harness complete and CI-gated with the fixtures backend and offline
  doubles; the CAPABILITY agreement number and prompt-compare diffs against a
  REAL backend need an LLM API key (or a local Ollama pull).
- Un-mock: `chief eval --backend deepseek` (or ollama/anthropic/openai) with
  `[llm].api_key` set in ~/.chief/config.toml; for prompt changes,
  `chief eval --compare v1 v2 --backend deepseek` and attach the report per
  CONTRIBUTING.md.

## Step 29 · Dual skill packaging — live-host halves (v3.1)
- Status: both SKILL.md files lint clean; `chief lite` transcripts in
  docs/skill-manual-tests.md are real output. The live halves need hosts this
  machine doesn't have: a local OpenClaw install (see Step 22 entry) and a
  Claude Code session with the skill loaded and API credentials.
- Un-mock: copy skills/claude-code/ into a project's .claude/skills/, run a
  watcher that finds something, verify the agent calls `chief lite` and obeys
  the route; for OpenClaw follow docs/openclaw-manual-test.md.

## Step 34 · Composio connector — live verification (v3.2)
- Status: adapter complete against Composio's documented v3 envelope +
  svix-style HMAC signatures; verified with signed fixtures (GitHub PR,
  Gmail, Slack triggers). A live round-trip needs a composio.dev account,
  a webhook subscription pointed at this machine (tunnel), and its secret.
- Un-mock: `chief connect composio --secret <whsec_...>`, subscribe
  triggers in the Composio dashboard to https://<tunnel>/v1/connectors/composio,
  fire a test trigger, watch `chief ui` History.
