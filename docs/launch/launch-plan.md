# Launch plan

Distribution is the bottleneck, not features. This is the order of operations
to get Chief in front of people, with the copy pre-written.

## Sequence

1. **Publish to PyPI** (`docs/PUBLISHING.md`) so `uvx agent-chief demo` works
   for everyone. Restore the PyPI badge afterward. *This gates everything else —
   the 60-second demo is the hook every post relies on.*
2. **Record the showcase GIF** (`make showcase`) and drop it at the top of the
   README (or keep the day-in-the-life `demo.gif` as the hero and add showcase
   below "How it decides").
3. **Publish the blog post**
   (`docs/blog/heartbeat-agents-are-training-you-to-ignore-them.md`) somewhere
   with a canonical URL: personal site, Dev.to, or a GitHub Pages/Medium mirror.
4. **Post it** — HN first (best signal), then X/Reddit, then the awesome-list PRs
   (`awesome-list-submissions.md`).

## Pre-written copy

### Hacker News (Show HN)
> **Show HN: Chief – a local-first attention layer that decides what deserves an interrupt**
>
> Your heartbeat agents report "all clear" every few hours until you stop
> reading — including the one time it mattered. Chief sits between you and
> everything competing for your attention (agents, CI, RSS, webhooks) and routes
> each event to interrupt / digest / dispatch / curate / drop.
>
> Three things I found worth writing up: a three-stage funnel so ~75% of events
> never reach an LLM; per-model, cache-aware cost accounting on every decision
> (`chief trace`); and a falsifiable preference-learning eval — feedback trains
> per-topic weights and `chief eval --learning` shows the agreement curve climb
> (with an honest note on where it can't).
>
> Local-first: one SQLite file, no cloud, no telemetry. Try it, zero keys:
> `uvx agent-chief demo`
>
> Repo + writeup: <link>

*HN tips: post Tue–Thu morning US time; reply to every comment; the title is the
whole game — lead with the concrete mechanism, not adjectives.*

### X / Twitter (thread opener)
> Ten helpful agents are a DoS attack on one human's attention.
>
> I built Chief: a local-first "prefrontal cortex" that decides what actually
> deserves to interrupt you — and *proves* it learns your preferences instead of
> just claiming to.
>
> 24 events in → interrupted once. 🧵

Follow-ups (one per idea): the funnel (75% never hit an LLM) · the cost trace
(the 17× pricing bug an AI reviewer caught) · the learning curve GIF · "try it:
uvx agent-chief demo".

### Reddit r/LocalLLaMA / r/selfhosted
Lead with local-first + Ollama-capable + no telemetry (that community's values),
then the demo command. Link the repo, not the blog, and let the README carry it.

## Interview framing (keep this handy)
Be able to whiteboard, from memory: the three-stage scoring + EMA weight update;
why EMA over anything heavier; and the **bounded-weight ceiling** the learning
eval exposes (stating a limit cold is the strongest signal in the interview).
The multi-agent adversarial review story (stored-XSS + 17× pricing bug) is the
best "how do you ensure quality" answer you have — rehearse it.
