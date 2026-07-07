# Your heartbeat agents are training you to ignore them

*Building an explainable, eval-driven attention layer for the age of agents.*

---

You gave an agent a job: watch the deploy, watch the inbox, watch the market.
So every few hours it reports in. *"All clear. Nothing to report."*

The first ten times, you read it. By the hundredth, your eyes slide past it.
And on the day it finally has something to say, you slide past that too —
because you've been **trained**, one "all clear" at a time, to treat that
sender as noise.

This isn't an agent problem. It's an attention problem, and more power on the
agent side makes it *worse*: ten agents each being helpful is a denial-of-service
attack on one human's prefrontal cortex.

I built **[Chief](https://github.com/SmileLikeYe/agent-chief)** to be that
prefrontal cortex — a local-first layer that sits between you and everything
competing for your attention, thinks for itself, and does exactly one of five
things with each event: **interrupt · digest · dispatch · curate · drop.**

This post is about the three engineering decisions that made it more than a
`if urgent: notify()` toy: **doing the cheap thinking first, pricing every
expensive thought, and proving the thing actually learns.**

## 1. Most events don't deserve an LLM

The naive design sends every candidate event to a model and asks "should I
interrupt?" That's slow, expensive, and — for the "all clear" flood — insulting
to the model. The 400th identical heartbeat does not require a frontier LLM to
adjudicate.

So Chief is a funnel, cheapest stage first:

- **Stage 1 — hard rules (µs).** Muted topics, dedup, quiet hours, and a
  *zero-information* detector that kills empty reports. (The detector requires
  **both** a regex hit **and** embedding similarity to a canned "empty report"
  set — so a security scan that merely *mentions* "all clear" still gets
  through. Cheap, but not dumb.)
- **Stage 2 — a similarity classifier (ms).** Looks-like-things-you-dismissed →
  drop; looks-like-things-you-engaged → route by history. Still no LLM.
- **Stage 3 — the LLM judge**, only for the genuinely novel, scoring five
  dimensions (urgency, relevance, actionability, novelty, confidence).

Run the deterministic day-in-the-life replay Chief ships with, and the funnel
pays off:

```
24 events in → 1 interruption
96% intercepted · only 25% of events ever reach the LLM
```

Three quarters of the traffic is settled for free, in microseconds, before a
token is spent. That's not an optimization bolted on later — it's the shape of
the whole system.

## 2. If a judgment costs money, account for it

The moment stage 3 involves a paid API, "should I interrupt?" has a dollar
figure attached. Most systems never look at it. Chief puts it on every decision.

Two engineering details made this honest rather than decorative:

**Prompt-cache-aware pricing.** The prompts are laid out `[system][context][user]`
— stable prefix first — so the system and context blocks are cache *hits* on
every call after the day's first. On DeepSeek's published rates a cache hit is
~4× cheaper than a miss, so the layout isn't cosmetic; it's most of the cost.
Chief models the split explicitly:

```
70% of judge input tokens are cache hits → ~$0.10 per 1,000 events
```

**Per-model, not per-provider, pricing.** This one is a trap I walked into and
an adversarial review caught: a naive price table keyed by *backend* bills a
`gpt-4o-mini` config at `gpt-4o` rates — a **~17× overcharge**. The fix is a
model-level table matched by ordered substring (real model ids look like
`claude-3-5-haiku-20241022`, so anchored prefixes miss them). Cost accounting
that's silently 17× off is worse than none.

Every decision then carries its full receipt, replayable after the fact:

```console
$ chief trace evt_20260706_1040_ab12
route dispatch at stage 3 in scene deep_work (confidence 0.85)
score 0.87  urgency=0.90 relevance=0.90 actionability=0.85 ...
┌────────────┬───────┬──────────────────────┐
│ stage      │    ms │ note                 │
│ stage1     │   0.1 │ no hard rule fired   │
│ judge      │ 812.4 │ backend deepseek     │
│ route      │   0.3 │ routed dispatch      │
└────────────┴───────┴──────────────────────┘
tokens: 1104 in (704 cached) / 96 out · cost $0.000301
```

No black boxes. Every route has a reason, five component scores, the rules it
matched, and what it cost.

## 3. "It learns your preferences" is a claim — so I made it falsifiable

Every product in this space says it "learns." Almost none show you the learning.
The signal is right there: when Chief interrupts you, you can tap **👍 worth it**
or **👎 don't bother me**. That's a reward. Per-topic weights are the policy. An
EMA update is the training. The loop is implied by the architecture — but does
it actually *close*?

So I built an eval that tries to falsify it. A simulated user has hidden
per-topic preferences. Chief starts blind (uniform weights) and is corrected
*only* by the ±1 signal — no labels, no gradient. We measure routing agreement
against the user's true preference, round over round:

```console
$ chief eval --learning
Routing agreement: 0% → 100% (+100%) · converged in 2 rounds
r 0 |                    | 0%
r 1 |█████████████████   | 86%
r 2 |████████████████████| 100%
```

The curve is monotonic *by construction* — feedback stops the instant a topic
is already routed correctly, so a learned preference can't regress — and it's
deterministic, so the number in this README is the number you'll get.

The interesting part is what the eval **refuses to claim.** Because the weights
are bounded, preference alone can't push an event with near-zero signal on
every dimension over the interrupt bar. I could have hidden that by cherry-picking
the test. Instead the harness documents the ceiling and a dedicated test pins
it. Feedback moves the *borderline* calls — which is precisely the job, since
stage-1 rules and clear scores already handle the obvious. **Being able to state
where your system stops working is more convincing than claiming it never does.**

## The part I didn't expect to matter most: reviewing it like an adversary

I built Chief with a swarm of review agents attacking each change from
independent angles — line-by-line, removed-behavior, cross-file, security,
conventions — then a separate verifier pass that only keeps findings it can
construct from the code. It found real things a single pass misses: a stored-XSS
path in the console that could exfiltrate the local API token, the 17× pricing
bug above, a degradation flag that lived in a namespace a webhook could
overwrite.

The lesson wasn't "AI finds bugs." It was that **adversarial, multi-perspective
review with a skeptical verifier catches a different and scarier class of bug
than tests do** — the ones where the code is doing exactly what you wrote, and
what you wrote is the problem.

## Where this nets out

Chief is ~300 offline tests, five routes, a three-stage funnel, per-model cost
accounting, a falsifiable learning loop, and a local console — all local-first:
one SQLite file and some markdown, no cloud, no telemetry.

But the three ideas travel beyond this one repo:

1. **Tier your compute by how much the decision is worth.** Don't send the 400th
   heartbeat to a frontier model.
2. **Price every expensive thought, per model, cache-aware — or don't claim to
   care about cost.**
3. **If you say your system learns, ship the eval that could prove it didn't.**

Try it in 60 seconds, no keys, fully offline:

```bash
uvx agent-chief demo
```

The code, the eval harness, and the spec it was built from step-by-step are all
at **[github.com/SmileLikeYe/agent-chief](https://github.com/SmileLikeYe/agent-chief)**.
