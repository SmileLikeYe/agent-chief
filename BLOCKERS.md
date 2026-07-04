# Blockers & Mocked Steps

Log of steps that needed human-only resources; implemented against mocks/fixtures per goal rule 3.

- Step 8: no live LLM API key (DeepSeek/Anthropic/OpenAI) and no local Ollama on this machine. All four adapters implemented and exercised against recorded HTTP cassettes (httpx.MockTransport); the ≥20/24 demo-agreement test uses cassettes synthesized from the demo fixture's judge blocks, so it validates the wire format + parsing + pipeline, not live model quality. To validate live: `chief init`, pick a backend, rerun tests with a key.
