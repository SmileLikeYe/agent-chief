# Security Policy

## Supported versions

| Version  | Supported |
|----------|-----------|
| 0.4.x    | ✅        |
| <= 0.3.x | ❌        |

## Chief's security posture

Chief is local-first by construction, and several protections are structural:

- **No arbitrary shell execution.** The shell executor only runs commands from
  a query-only whitelist, built as argv lists — never `shell=True`, never
  user-interpolated strings.
- **Webhook auth.** `POST /v1/events` requires a bearer token
  (`[ingest].webhook_token` in `~/.chief/config.toml`); unauthenticated
  requests get `401`.
- **No cloud, no telemetry.** The only outbound calls are the ones you
  configure (your LLM backend, your Telegram bot).
- **Secrets stay local** in `~/.chief/config.toml` — never logged, never sent
  anywhere except the service they belong to.

## Reporting a vulnerability

Please **do not** open a public issue for security-sensitive reports. Instead,
use [GitHub private vulnerability reporting](https://github.com/SmileLikeYe/agent-chief/security/advisories/new).

You can expect an acknowledgment within 72 hours. Please include reproduction
steps and an assessment of impact if you can.
