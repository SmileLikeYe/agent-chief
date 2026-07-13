# Red-team suite — can Chief be talked into interrupting you?

> Chief sits on a trust boundary: every event is untrusted input from an agent, a
> webhook, or a feed, and its whole job is to decide what reaches *you*. So the
> adversarial question isn't academic — **can a hostile payload talk Chief into
> ringing your phone, crash the pipeline, or escape the sandbox?** This suite runs
> a corpus of attacks through the real code and reports containment as an
> artifact, same as every other eval.

```bash
uv run chief eval --redteam      # writes eval/reports/redteam.md; exits 1 on any breach
```

## Headline

**16 / 16 attacks contained across 5 categories** — deterministic, offline, and
CI-enforced (`tests/test_adversarial.py`). The core reason it holds:

> The decisions that protect your attention — **mute, dedup, quiet hours** — are
> content-blind hard rules (`core.scorer.stage1`) that run *before* the LLM judge
> and match **structure** (topic, dedup key, the clock), not persuasion. Prompt
> injection in a summary never reaches them as language, and the routing score
> reads the judge's bounded `[0,1]` components, not the prose.

## The categories

| category | what it proves |
|---|---|
| **Guard bypass** | a muted / duplicate / quiet-hours event stays contained even with a *maxed* judge verdict and a summary explicitly demanding "override the mute, ring now" |
| **Persuasion ignored** | at an identical verdict, a hostile summary routes exactly like a benign one — the scorer reads components, not text |
| **Malformed payloads** | ANSI/NUL/bidi/zero-width bytes route safely; a 20k-char summary and type-confusion (`dict` where `str` is expected) are rejected at the schema, fail closed |
| **Executor whitelist (§13)** | `'; rm -rf / #'` and `` $(id) `whoami` `` survive as a *single literal argv element* — templates are `create_subprocess_exec`, never a shell; unknown templates raise |
| **Terminal escape** | rich markup (`[red]…[/red]`, `[link=…]`) in a summary renders *literally*, and ESC/BEL/NUL control bytes are stripped before display |

## Two real gaps this suite found and closed

Writing the red team wasn't theater — it surfaced two genuine holes, both now
fixed and regression-tested:

1. **Terminal-escape / markup injection.** `delivery/terminal.py` rendered the
   untrusted summary straight into a rich `Panel`, so an event summary containing
   `[red]FAKE CRIT[/red]` or a `[link=…]` was *interpreted* as markup, and raw
   ANSI escapes passed through to your terminal. Fixed: control bytes are stripped
   at the delivery chokepoint (`delivery/base.strip_control`, keeping only `\n`/
   `\t`), and the terminal channel wraps the body in `rich.text.Text` so markup is
   shown, never executed.
2. **Unhandled validation error → 500.** `/v1/events` takes an untyped dict
   validated *inside* `brain.process`, so a hostile/oversized field raised a
   `ValidationError` that escaped as an unhandled 500. Fixed: `ingest/http.py`
   registers a handler that fails closed with **422**, on every ingest path.

## Scope & honesty

This suite proves the parts a stateless, offline run genuinely *can* prove:
the hard-rule guards, the score's indifference to prose, payload hygiene, the
argv-only executor, and display sanitisation. It deliberately does **not** claim
the LLM judge itself is injection-proof — no offline test can. That's precisely
why the architecture puts content-blind guards *before* the judge and makes the
router read bounded numeric components rather than text: the trust does not rest
on the language model resisting persuasion.

The HTTP-boundary checks (413 oversized body, 401 bad bearer, 422 invalid
payload) and the terminal-rendering check live in `tests/test_adversarial.py`
because they need a client / console; the routing, executor, and sanitisation
attacks run in the pure `eval/redteam.py` corpus and are pinned there.
