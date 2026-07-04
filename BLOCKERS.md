# Blockers & Mocked Steps

Log of steps that needed human-only resources; implemented against mocks/fixtures per goal rule 3.

- Step 8: no live LLM API key (DeepSeek/Anthropic/OpenAI) and no local Ollama on this machine. All four adapters implemented and exercised against recorded HTTP cassettes (httpx.MockTransport); the ≥20/24 demo-agreement test uses cassettes synthesized from the demo fixture's judge blocks, so it validates the wire format + parsing + pipeline, not live model quality. To validate live: `chief init`, pick a backend, rerun tests with a key.
- Step 9: sentence-transformers/torch cannot be installed on this machine — disk has <1GB free and CPU torch alone needs ~2GB. The `embeddings` extra + SentenceTransformerEmbedder wiring is implemented and the fallback path is tested; all similarity tests run on the deterministic HashEmbedder. To validate the real model: free ~3GB, `uv sync --extra embeddings`, rerun pytest.
- Step 10: headless dev machine has no notification daemon; DesktopChannel's plyer path is unit-tested with an injected notify_fn and the real path was smoke-tested to degrade gracefully to terminal.
