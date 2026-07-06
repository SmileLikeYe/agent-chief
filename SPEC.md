# Chief — The Chief of Staff for Your Agents · Implementation Spec v3

> This is the complete engineering spec, written for an AI coding agent (Claude Code) to implement **step by step**.
> **Rule of execution: ONE STEP = ONE COMMIT.** Do not batch steps. Do not skip ahead.
> Working name: `chief`. Repo name candidates (check availability): `agent-chief` / `chiefd` / `cortexd`.

---

## 0. Product Definition

**Chief is the Chief of Staff for all your agents and information sources.** Everything flows into it; it thinks for itself; then it does one of three things:

1. **🔔 Interrupt** the human — only when worth it, at the right moment, and *arriving with a plan*.
2. **🤖 Dispatch** work to downstream agents — and verify results before reporting.
3. **📚 Curate** into memory — facts and intents that aren't worth mentioning now, waiting to be connected later.

Positioning:
- Not another agent platform (OpenClaw is the limbs and channels; **Chief is the prefrontal cortex**).
- Chief does not build pipes. It defines a standard ingest protocol; any source connects itself.
- The interrupt decision is always two-axis: **content worthiness × scene tolerance**.

Hooks:
- EN: `Your agents don't need more power. They need a chief of staff.`
- The "kill 'all clear' reports" feature deserves its own README section — every heartbeat user has suffered this.

## 1. Design Principles (highest authority during implementation)

1. **Time-to-first-wow < 60s.** `uvx chief demo` must work with zero keys / zero config. Reject any design that adds friction to first contact.
2. **Default to not interrupting.** Under any uncertainty (low-confidence scene, borderline score), degrade to a gentler route. The trust damage of a false interrupt is asymmetric to a missed one.
3. **Policy is readable and editable.** Everything learned distills into `POLICY.md`. Manual edits take top priority, effective immediately.
4. **Local-first.** User model, memory, feedback all live locally (SQLite + markdown). LLM judge is pluggable: local (Ollama) or cloud (DeepSeek / Anthropic / OpenAI).
5. **Dispatch must be verified.** An agent claiming "done" is a claim, not a proof. Every dispatch result passes a verifier before it is reported.
6. **Small and sharp.** Anything in §13 (out of scope) must not appear in code; new ideas go to `ROADMAP.md`.

## 2. Architecture

```
sources/agents ──▶ Ingest ──▶ Brain Loop ──┬─▶ 🔔 Interrupt (with a plan)
 (webhook/MCP/built-ins)  (triage→associate→decide) ├─▶ 🤖 Dispatch (verify, then report)
                                ▲                   └─▶ 📚 Curate (memory)
                                │                            │
                     Scene Engine + Memory ◀─────────────────┘ (recalled by future events)
                                ▲
                     Feedback loop (user reactions / dispatch results)
```

Runtime: one resident process (`chief run`) = async event loop + scheduled jobs (digest, nightly distillation).

## 3. Data Models (`core/schema.py`, all pydantic)

```python
class Event(BaseModel):
    id: str                      # evt_{yyyymmdd}_{hhmm}_{4hex}, generated at ingest
    source: str                  # submitter id, e.g. "flight-watcher"
    topic: str                   # hierarchical, e.g. "travel.flight_change"; unit of learning
    summary: str                 # <= 200 chars
    detail: str | None = None
    suggested_action: str | None = None      # actionability source
    evidence: list[str] = []                 # urls or local paths
    claimed_urgency: Literal["low","medium","high"] | None = None  # advisory only, never trusted
    expires_at: datetime | None = None       # value-decay deadline
    dedup_key: str | None = None             # hash of summary if absent
    received_at: datetime

class Decision(BaseModel):
    event_id: str
    route: Literal["interrupt","digest","dispatch","curate","drop"]
    score: float | None = None
    components: dict[str, float] | None = None  # urgency/relevance/actionability/novelty/confidence
    scene: str
    scene_confidence: float
    cost: float
    matched_rules: list[str] = []
    reason: str                  # one line; goes to audit log and user-facing explanation
    stage: int                   # 1=hard rules, 2=classifier, 3=LLM judge
    dispatch_task_id: str | None = None

class Task(BaseModel):
    id: str
    origin_event_id: str
    goal: str                    # objective for the executor agent
    executor: Literal["claude_code","openclaw","shell","noop"]
    acceptance: str              # natural-language acceptance criteria
    acceptance_cmd: str | None = None   # if present, exit code 0 = pass
    status: Literal["pending","running","done","failed","rejected"] = "pending"
    result_summary: str | None = None
    attempts: int = 0            # max 2; then downgrade to interrupt (ask the human)

class MemoryItem(BaseModel):
    id: str
    origin_event_id: str | None
    text: str                    # one-line fact/intent, e.g. "user wants to watch XX's next SDK release"
    topic: str
    embedding: list[float]
    created_at: datetime
    last_hit_at: datetime | None = None
    hit_count: int = 0
    ttl_days: int = 90           # expired items move to archive table, excluded from association

class SceneState(BaseModel):
    scene: Literal["sleeping","deep_work","meeting","commuting","social","leisure","idle"]
    confidence: float            # < 0.6 = low confidence → downgrade route one level
    signals: dict[str, Any]      # raw provider snapshot, for audit
    at: datetime
```

Storage: single SQLite file `~/.chief/state.db` with tables `events, decisions, tasks, memory, memory_archive, feedback, topic_weights, scene_log`; plus `~/.chief/POLICY.md` and `~/.chief/USER.md` (profile summary).

## 4. Module Specs

### 4.1 Ingest (`ingest/`)
- **HTTP webhook**: `POST /v1/events` (Event without id/received_at) → returns Decision. Default port 8787, simple bearer token.
- **MCP server** (fastmcp), tools: `propose(event) -> Decision`, `feedback(event_id, signal)`, `digest(now=False)`, `policy(action, text?)`, `stats(days=7)`.
- **Built-in zero-config sources** (`ingest/sources/`, independent coroutines):
  - `github_notifications`: via `gh api notifications` (offered in wizard when `gh auth` detected), poll 5 min.
  - `rss`: any RSS url pasted in wizard, poll 30 min.
  - Sources ONLY fetch → convert to Event → submit through the unified entry. No judgment logic inside sources.
- Normalization at entry: generate id, fill dedup_key, infer missing topic via cheap LLM call (cached).

### 4.2 Brain Loop (`core/brain.py`)
For each incoming Event, in order:
1. **Triage**: dedup by dedup_key within 24h; merge events with same topic AND embedding cosine > 0.92 within a 10-min window (concat summaries, merge evidence).
2. **Associate**: query memory top-3 by event embedding (cosine > 0.78); on hit, inject MemoryItem.text into decision context, update hit stats. A memory hit boosts relevance (see 4.4).
3. **Decide**: get SceneState from the scene engine, run the worthiness engine (4.4), produce Decision, route (4.5).
4. Full audit trail: `decisions` table + `~/.chief/logs/audit.jsonl`.

### 4.3 Scene Engine (`context/`)
Provider interface:
```python
class ContextProvider(Protocol):
    name: str
    def sample(self) -> dict[str, Any]: ...
```
v1 built-in providers (graceful degradation per platform; unavailable → skip):

| provider | signals | implementation |
|---|---|---|
| clock | local time, quiet-hours flag | pure code |
| calendar | current / next-15-min event type | ics url or gcal (optional) |
| os_focus | macOS Focus / Windows DND | macOS via defaults/Shortcuts bridge; skip if unreadable |
| screen_lock | screen locked? | per-platform API |
| activity | keyboard/mouse idle seconds | per-platform API |
| foreground_app | app name only (never content) | macOS NSWorkspace; opt-in, default OFF |

Inference rules (`context/infer.py`, pure rules, 30s cache):
```
sleeping   : quiet hours AND screen locked > 30min                          conf 0.9
meeting    : calendar meeting in progress OR foreground = meeting app       conf 0.85
deep_work  : calendar focus block OR (foreground=IDE AND >25min AND active) conf 0.75
commuting  : v1: calendar "commute" event only                              conf 0.7
social     : DND=personal mode OR weekend evening + mobile active           conf 0.5
leisure    : foreground = entertainment app OR weekend daytime idle         conf 0.6
idle       : fallback                                                       conf 0.4
```
- confidence < 0.6 → interrupt auto-degrades to digest (Principle 2).
- Scene policy table (defaults; overridable in POLICY.md):

| scene | interrupt threshold | max delivery level | outside night whitelist |
|---|---|---|---|
| sleeping | 0.95 | ring | → digest |
| meeting | 0.90 | silent push | |
| deep_work | 0.85 | silent push | |
| commuting | 0.60 | ring (voice-friendly summary) | |
| social | 0.70 | vibrate | |
| leisure | 0.50 | vibrate | |
| idle | 0.45 | ring | |

Delivery levels: terminal print < desktop notification < Telegram silent < Telegram ring.

### 4.4 Worthiness Engine (`core/scorer.py`, three stages)
- **Stage 1 — hard rules** (µs): quiet hours (except night-whitelist topics) → digest; muted topics → drop; dedup → drop; zero-information templates (regex `all (good|clear|normal)|nothing (new|to report)|check(ed)? complete` + embedding similarity > 0.85 against a canned "empty report" set, both required) → drop; POLICY.md user rules → direct route.
- **Stage 2 — cheap classifier** (ms): compare against `engaged_set` / `dismissed_set` historical vectors. dismissed-sim > 0.88 with no engaged record → drop; engaged-sim > 0.88 → skip judge, route by historical same-class mean; otherwise → stage 3.
- **Stage 3 — LLM judge**: pluggable backends (`judge/`: ollama / deepseek / anthropic / openai adapters). System prompt is a **stable prefix** (prompt-caching friendly):

```
[system]  (stable, cacheable)
You are the gatekeeper of the user's attention. Your sole duty is to protect it.
Your default answer is "do not disturb".
For each candidate event output JSON:
{"urgency":0-1,"relevance":0-1,"actionability":0-1,"novelty":0-1,"confidence":0-1,
 "dispatchable":true|false,"dispatch_goal":"one-line goal if dispatchable else null",
 "memorize":"one-line fact/intent worth remembering, else null",
 "reason":"one line"}
urgency = does value decay with time; relevance = match to user's goals;
actionability = what the user can do right now; novelty = new info vs recently delivered;
confidence = verifiability of evidence;
dispatchable = is there prep work an agent can complete without the user.
Output JSON only. Exaggeration and flattery are dereliction of duty. Temperature 0.

[context]  (semi-stable, cache per day)
User profile: {USER.md summary}
Recently delivered: {summaries of last-24h interrupt+digest}
Associated memory: {hit MemoryItem.text, or "none"}

[user]  (per call)
Current scene: {scene} (confidence {conf})
Candidate event: {Event JSON}
```
- Composition: `score = Σ(w_topic[dim]·comp[dim]) − scene_cost`; on memory hit, relevance ×1.2 (cap 1.0).
- Routing: `score ≥ scene threshold → interrupt; 0.40–threshold → digest; < 0.40 with no lasting value → drop; < 0.40 but memorize != null → curate`.
- If `dispatchable=true` and route ∈ {interrupt, digest}: run dispatch FIRST, merge result into the event, then deliver ("arrive with a plan"). **Dispatch timeout 10 min → deliver as-is, never block.**

### 4.5 Three Output Paths
**Interrupt (`delivery/`)**: deliver at the level allowed by the scene policy. Message template: `{summary}\n{plan (if dispatch result)}\n[Do it] [Later] [Mute this kind]` — the three buttons ARE the feedback capture. v1 channels: terminal, desktop (`plyer`), Telegram bot.

**Dispatch (`dispatch/`)**:
- executor=claude_code: subprocess `claude -p "{goal}\nAcceptance: {acceptance}" --output-format json`, configurable workdir.
- executor=openclaw: write into OpenClaw's task-injection interface (implemented inside the skill).
- executor=shell: whitelisted command templates only (v1 ships read-only/query templates; arbitrary shell is forbidden).
- **Verification**: if `acceptance_cmd` present → run it, exit 0 = pass; else LLM second-opinion ("Does this result satisfy the acceptance criteria? Answer pass/fail + one reason"). fail → retry once → fail again → downgrade to interrupt asking the human.

**Curate (`memory/`)**: `memorize != null` → store MemoryItem (local embedding: `sentence-transformers/bge-small-en-v1.5`; use `bge-m3` for mixed Chinese-English, configurable). At digest time, run one batch association pass over the day's digest pool; cross-event combinations become the digest's **"Connections"** section.

### 4.6 Feedback & Learning (`core/learner.py`)
Signal enum for `feedback` table:

| signal | trigger | effect |
|---|---|---|
| acted | tapped [Do it] / clicked link | topic 5-dim weights EMA positive α=0.2; add to engaged_set |
| read | expanded > 10s | weak positive α=0.1 |
| promote | digest item "should have pinged me" | urgency weight +0.3 (capped) |
| dismissed_fast | swiped away < 30s | negative α=0.2; add to dismissed_set |
| muted | [Mute this kind] / natural language | topic muted in POLICY.md, effective immediately |
| timeout | interrupt with no reaction 24h | weak negative α=0.05 |
| task_ok / task_fail | dispatch verification result | adjust dispatch propensity for executor+topic |

- Threshold tuning: 7-day interrupt dismissed_fast ratio > 40% → global threshold +0.02/day; < 15% → −0.01/day; bounded [0.35, 0.95].
- **Nightly distillation** (03:00): LLM translates the day's weight changes into one human-readable line appended to POLICY.md, format `- {rule} (learned {date}, source: {stats})`. Unparseable POLICY lines are ignored with a warning, never crash.
- **Shadow mode**: first 7 days (or until 50 feedback samples), every interrupt degrades into the digest, annotated `⚡ would have: interrupted you (score x.xx, scene xx)`, with ✓/✗ quick-grade buttons. Graduation produces a **Tact Report**.

### 4.7 Demo Replay Mode (`demo/`) — TOP PRIORITY FEATURE
`uvx chief demo`: zero dependencies (no keys; judge uses pre-recorded fixture results — fully offline). Replays "a day in the life of an engineer" at 1 event / 2s, rich-rendered route + reason per event, ends with the Tact Report.

Fixture `demo/day_of_engineer.json`, 24 events. Anchor points (fill remaining 14 with realistic noise — newsletters, dependency-update notices, calendar reminders — keeping dramatic pacing: setup #5 → payoff #19):

| # | time | event | expected decision | dramatic beat |
|---|---|---|---|---|
| 1 | 07:10 | heartbeat "all clear" | 🗑 drop | opening statement: kill empty reports |
| 3 | 08:00 | digest time | 📰 digest sent (4 overnight items) | waking-up scene |
| 5 | 09:30 | user tells an agent "remember to check XX's next SDK release" | 📚 curate | plant the setup |
| 8 | 10:15 | deep_work; newsletter arrives | 📰 digest | scene protection |
| 9 | 10:40 | deep_work; CI fails on main | 🤖 dispatch(claude_code fix) → verify pass → silent push "fixed, PR awaiting review" | dispatch + verify + plan |
| 13 | 12:30 | competitor ships new version | 📰 digest | |
| 16 | 14:00 | meeting; flight delayed 2.5h | 🤖 dispatch rebooking lookup first → 🔔 silent push with 3 options | two-axis + arrive with a plan |
| 19 | 16:20 | RSS: "XX releases SDK 2.0" | association hits #5 → 🤖 dispatch summary → 📰 evening digest "Connections" | proof of thinking |
| 21 | 19:00 | another "all clear" | 🗑 | callback |
| 24 | 23:30 | sleeping; marketing email | 🗑 | closing |

Final report: `Today: 24 events in → 14 blocked · 6 batched · 3 handled (all verified) · interrupted you exactly once.`
Demo exit line: `Connect real sources? Run: chief init`

### 4.8 Onboarding (`cli/init.py`)
`uvx chief init` interactive wizard (questionary), every question skippable with sensible defaults:
1. LLM backend (default local if ollama detected; else guide DeepSeek/Anthropic key entry)
2. Delivery channel (default desktop; Telegram needs bot token — link a 30s illustrated guide)
3. Digest times (default 08:00 / 18:30)
4. Quiet hours (default 23:00–08:00) + night whitelist topics (default: family, production_incident)
5. Detect `gh auth status` → one-click GitHub notifications; ask for RSS url (skippable)
Generates `~/.chief/config.toml` + initial POLICY.md + USER.md template; then `chief run`. `chief install-service` emits launchd/systemd units.

### 4.9 OpenClaw Skill (`skills/openclaw/`)
SKILL.md instruction: when heartbeat finds something worth telling the user, it MUST NOT message directly; it calls Chief's MCP `propose` and obeys the returned Decision. Include a delivery callback script so interrupts ride OpenClaw's existing channels.

## 5. CLI Surface
```
chief demo                 # offline replay (§4.7)
chief init                 # wizard (§4.8)
chief run                  # resident process
chief digest --now
chief status               # scene / queue / today's stats
chief policy [edit|show]
chief report [--days 7]    # Tact Report
chief install-service
```

## 6. Repo Layout
```
chief/
├── README.md            # hook + demo GIF + 60s quickstart + 3-tier showcase links
├── SPEC.md              # this document
├── PROGRESS.md          # step tracking table (see §8)
├── ROADMAP.md
├── pyproject.toml       # uv-managed; entry chief=cli.main:app (typer)
├── cli/                 # main.py, init.py
├── core/                # schema.py, brain.py, scorer.py, learner.py, state.py
├── context/             # providers/*.py, infer.py
├── judge/               # base.py, ollama.py, deepseek.py, anthropic.py, openai.py, fixtures.py, prompts.py
├── ingest/              # http.py, mcp_server.py, sources/{github.py, rss.py}
├── dispatch/            # executor.py, acceptance.py
├── memory/              # store.py, associate.py
├── delivery/            # terminal.py, desktop.py, telegram.py
├── demo/                # day_of_engineer.json, runner.py
├── skills/openclaw/     # SKILL.md, hook.py
├── policy/              # POLICY.template.md, USER.template.md
├── tests/
└── docs/                # architecture.md, protocol.md (the ingest protocol, standalone), decisions.md (ADRs)
```
Stack: Python 3.12 + uv + typer + pydantic + fastmcp + FastAPI (webhook) + aiosqlite + sentence-transformers + rich + questionary + plyer + python-telegram-bot.

## 7. Execution Rules for the Coding Agent

1. **ONE STEP = ONE COMMIT.** Complete a step, make all its tests pass, commit with the exact message given, update PROGRESS.md in the same commit, then move on. Never batch, never skip.
2. Write the test skeleton for a step BEFORE its implementation. The acceptance criteria of each step ARE its test cases.
3. On any decision this spec doesn't cover: choose the simpler option and record a one-line ADR in `docs/decisions.md`.
4. All LLM prompts live in `judge/prompts.py`. No prompt strings scattered elsewhere.
5. Every module docstring's first line cites the spec section it implements (e.g. `Implements SPEC §4.3`).
6. Anything listed in §13 appearing in code is a violation. New ideas → ROADMAP.md.

## 8. PROGRESS.md Format

Maintain this table; update the row in the same commit that completes the step:

```markdown
| Step | Title | Status | Commit | Date |
|------|-------|--------|--------|------|
| 1 | Project scaffold | ✅ | abc1234 | 2026-07-06 |
| 2 | Core schemas & storage | ⏳ in progress | | |
| 3 | ... | ⬜ | | |
```

## 9. Implementation Steps

> Priority order = step order. Phase 1 delivers the offline demo (the wow); Phase 2 makes it real; Phase 3 makes it think and act; Phase 4 ships it.

### Phase 1 — Brain Trunk & Offline Demo (Steps 1–7)

**Step 1 · Project scaffold**
- pyproject (uv), typer CLI skeleton with all §5 subcommands stubbed, repo layout of §6 with empty modules, pytest + ruff configured, GitHub Actions CI (lint + test), PROGRESS.md initialized.
- Accept: `uvx --from . chief --help` lists all subcommands; CI green on empty test suite.
- Commit: `chore: project scaffold, CLI skeleton, CI`

**Step 2 · Core schemas & storage**
- All §3 pydantic models; aiosqlite state layer creating the 8 tables; audit JSONL writer.
- Accept: round-trip tests for every model (create → persist → load → equality); db file created at configured path.
- Commit: `feat(core): schemas and sqlite state layer`

**Step 3 · Stage-1 hard rules + POLICY.md parser**
- Quiet hours, muted topics, dedup, zero-information detection (regex + canned-set embedding, both required), POLICY.md user-rule parsing (bad lines ignored with warning).
- Accept: table-driven tests covering every rule, incl. night-whitelist passthrough and unparseable POLICY lines.
- Commit: `feat(scorer): stage-1 hard rules and policy parser`

**Step 4 · Scene engine (clock + calendar) + inference + policy table**
- Provider protocol; clock & calendar providers; §4.3 inference rules with confidence; scene policy table with POLICY.md override; low-confidence downgrade.
- Accept: frozen-time tests produce expected SceneState for each of the 7 scenes; confidence 0.5 forces interrupt→digest downgrade.
- Commit: `feat(context): scene engine with pluggable providers`

**Step 5 · Judge interface + fixture backend + scoring & routing**
- `judge/base.py` interface; `judge/fixtures.py` (returns pre-recorded component scores keyed by event id — powers the offline demo); §4.4 composition, thresholds, routing incl. curate branch and dispatch flagging (dispatch itself stubbed as noop).
- Accept: routing unit tests for all five routes; memory-hit relevance boost verified with a mocked hit.
- Commit: `feat(judge): scoring composition and routing with fixture backend`

**Step 6 · Demo fixture + replay runner**
- Complete 24-event `day_of_engineer.json` per §4.7 (fill the 14 noise events; keep pacing); rich-rendered replay at 1 event/2s with `--fast` flag for tests; final Tact Report rendering.
- Accept: `chief demo` runs fully offline end-to-end; visual smoke test via `--fast`.
- Commit: `feat(demo): offline day-of-engineer replay`

**Step 7 · Demo routing regression (full-table)**
- `tests/test_demo_routing.py`: assert the route of ALL 24 events matches the fixture's expected table; this is the permanent regression harness.
- Accept: full-table assertion green; intentionally flipping one expected route makes it fail.
- Commit: `test(demo): full-table routing regression`

🏁 **Phase 1 gate: `uvx chief demo` delivers the 60-second wow, fully offline.**

### Phase 2 — Real Judge, Delivery, Feedback (Steps 8–13)

**Step 8 · Real LLM judge backends**
- ollama / deepseek / anthropic / openai adapters behind the Step-5 interface; §4.4 prompt in `prompts.py` with stable-prefix structure; config-driven selection; JSON-mode + retry-on-malformed.
- Accept: against a live backend (or recorded HTTP cassettes), demo-script routing agreement ≥ 20/24; malformed-JSON retry test.
- Commit: `feat(judge): ollama/deepseek/anthropic/openai backends`

**Step 9 · Stage-2 embedding classifier**
- Local embedding model wiring; engaged/dismissed vector sets; §4.4 stage-2 shortcuts; triage-merge (§4.2 step 1) now using real embeddings.
- Accept: seeded-set tests for both shortcut paths and pass-through; merge test for near-duplicate events.
- Commit: `feat(scorer): stage-2 similarity classifier and triage merge`

**Step 10 · Delivery: terminal + desktop**
- Delivery-level abstraction per §4.3 table; terminal and plyer desktop channels; scene-capped level selection.
- Accept: level-capping unit tests (meeting caps at silent push); manual smoke on dev machine.
- Commit: `feat(delivery): terminal and desktop channels with level caps`

**Step 11 · Delivery: Telegram + feedback buttons**
- Bot channel; silent vs ring modes; `[Do it][Later][Mute this kind]` inline buttons wired to feedback capture.
- Accept: integration test with telegram test double: button callback → correct signal row in feedback table.
- Commit: `feat(delivery): telegram channel with inline feedback`

**Step 12 · Learner: signals, EMA, threshold tuning**
- Full §4.6 signal table; EMA weight updates; bounded global threshold tuning; engaged/dismissed set maintenance from signals.
- Accept: simulated 4× dismissed_fast on one topic measurably lowers its future score; threshold bounds respected under extreme ratios.
- Commit: `feat(learner): feedback signals and weight adaptation`

**Step 13 · Shadow mode + Tact Report**
- 7-day/50-sample shadow gating; digest annotation with would-have decisions and ✓/✗ grading; graduation report; `chief report`.
- Accept: time-travel test: shadow → feed 50 graded samples → graduates → real interrupts enabled; report renders correct counts.
- Commit: `feat(learner): shadow mode and tact report`

🏁 **Phase 2 gate: real LLM decisions delivered to a real phone, learning from real reactions.**

### Phase 3 — Dispatch, Memory, Ingest (Steps 14–20)

**Step 14 · Dispatch executors (claude_code + shell whitelist)**
- Task lifecycle; claude_code subprocess executor; shell whitelist templates (query-only); attempts/downgrade plumbing.
- Accept: fake-executor lifecycle tests pending→running→done/failed; whitelist rejects non-template commands.
- Commit: `feat(dispatch): task lifecycle and executors`

**Step 15 · Dispatch verification**
- acceptance_cmd runner; LLM second-opinion verifier; retry-once-then-ask-human downgrade.
- Accept: cmd pass/fail paths; LLM-verifier fail → retry → downgrade produces an interrupt asking the human.
- Commit: `feat(dispatch): verification and downgrade`

**Step 16 · Arrive-with-a-plan**
- `dispatchable` flow: dispatch before delivery, merge result into message, 10-min timeout delivers as-is (never block).
- Accept: timeout test (mock slow executor) delivers original within deadline; happy path shows plan in message.
- Commit: `feat(brain): plan-attached interrupts`

**Step 17 · Memory: curate + associate**
- MemoryItem store with TTL/archive; brain-loop association (§4.2 step 2) with relevance boost; digest-time batch association → "Connections" section.
- Accept: replay #5→#19 chain with real embeddings: curate then hit then Connections entry; TTL expiry excludes archived items.
- Commit: `feat(memory): curation and association`

**Step 18 · Ingest protocol: webhook + MCP**
- FastAPI `POST /v1/events` with bearer auth; fastmcp server exposing §4.1 tools; entry normalization incl. topic inference.
- Accept: `curl` round-trip returns valid Decision; MCP tools exercised via client test; missing-topic event gets inferred topic.
- Commit: `feat(ingest): webhook and MCP endpoints`

**Step 19 · Built-in sources: GitHub + RSS**
- gh-notifications and RSS pollers as pure fetch→Event converters.
- Accept: fixture-fed converter tests produce well-formed Events; poller respects intervals (mock clock).
- Commit: `feat(ingest): zero-config github and rss sources`

**Step 20 · Onboarding wizard + service install**
- §4.8 wizard; config.toml generation; `install-service` units; `chief run` wiring everything.
- Accept: scripted wizard run (pexpect) on clean HOME produces working config; fresh-machine path to first real decision < 10 min (manual check, documented).
- Commit: `feat(cli): onboarding wizard and service install`

🏁 **Phase 3 gate: a stranger can install, connect a real source, and watch Chief think, dispatch, and remember.**

### Phase 4 — Ecosystem & Release (Steps 21–24)

**Step 21 · Digest polish + nightly distillation**
- Digest with Connections section and shadow annotations; 03:00 distillation job appending human-readable POLICY lines.
- Accept: distillation test turns a weight-change log into a well-formed POLICY line; digest golden-file test.
- Commit: `feat(digest): connections section and nightly distillation`

**Step 22 · OpenClaw skill**
- SKILL.md + hook per §4.9; delivery callback riding OpenClaw channels.
- Accept: skill lint passes; documented manual test transcript against a local OpenClaw.
- Commit: `feat(skills): openclaw integration`

**Step 23 · Docs + README**
- README (hook, demo GIF placeholder, 60s quickstart, kill-all-clear section, shadow-mode trust story); docs/protocol.md ("How to connect your agent to Chief" — the protocol-definer artifact); docs/architecture.md.
- Accept: README quickstart verified on clean machine < 60s to demo; protocol.md sufficient for a third party to POST a valid event without reading source.
- Commit: `docs: readme, ingest protocol, architecture`

**Step 24 · Release assets**
- Demo GIF generation script (vhs or asciinema+agg), reproducible; version 0.1.0 tag; release checklist (ClawHub submission, awesome-list PRs).
- Accept: `make demo-gif` reproduces the README GIF; `uvx agent-chief demo` works from the published package (test PyPI).
- Commit: `chore(release): v0.1.0 demo assets and checklist`

### Phase 5 — Trust & Distribution (v3.1 amendment, Steps 25–31)

> v3.1 execution order interleaves these with the original steps:
> 8 → 9 → 10 → 11 → 12 → 13 → **25 → 26 → 27 → 28** → 14 → 15 → 16 → 17 →
> 18 → 19 → 20 → **29 → 30** → 21 → 23 → **31** → 24.
> Original Step 22 is absorbed by Step 29 (mark "merged into 29" in
> PROGRESS.md). Hostile reviews after Steps 13, 28, 20, and 31.

**Step 25 · Golden dataset + eval harness**
- Build `eval/golden.jsonl`: ~200 labeled events (expand from the demo fixture + synthesize diverse scenes/topics/edge cases), each with expected route and a one-line rationale.
- Eval runner computes routing agreement rate, bucketed by route / topic / scene. Strictly separate CAPABILITY evals (golden set, improvable, report the number) from REGRESSION evals (the demo 24, must stay 100%, wired into CI).
- CLI: `chief eval [--backend X]` → markdown report to eval/reports/.
- Accept: fixture backend scores 100% on regression; a real backend produces a bucketed agreement report; CI fails if regression < 100%.
- Commit: `feat(eval): golden dataset and evaluation harness`

**Step 26 · Decision trace + cost accounting**
- Every Decision records: per-stage latency, tokens in/out, cached tokens (read from API usage fields), and USD cost via a per-backend price table (model DeepSeek cache-hit vs cache-miss pricing explicitly).
- CLI: `chief trace <event_id>` replays the full decision chain (stages, rules matched, scores, prompt version, cost).
- Tact Report gains a cost dimension: % events reaching LLM, cache hit rate, total judgment cost.
- Accept: trace renders a complete chain; unit tests for cost math incl. cache-hit/miss price gap; report shows all three metrics.
- Commit: `feat(trace): decision tracing and cost accounting`

**Step 27 · Prompt governance**
- Migrate all prompts in judge/prompts.py to versioned Jinja2 templates (provider-agnostic variables). Prompt version is stamped into every Decision audit record.
- `chief eval --compare <promptV1> <promptV2>` produces a diff report: agreement delta + list of flipped samples.
- Rule (add to CONTRIBUTING.md): no prompt change merges without an eval diff report.
- Accept: changing one word in a template yields a diff report with flipped samples; version appears in audit log.
- Commit: `feat(judge): versioned prompt templates with eval-gated changes`

**Step 28 · Failure injection + graceful degradation**
- Chaos tests: judge returns malformed JSON, times out, or the backend is fully down.
- Degradation policy: when no backend is available, fall back to rules-only conservative routing (all borderline events → digest, never interrupt), mark decisions `degraded=true` in audit, auto-recover when backend returns. `chief status` shows degradation state.
- Accept: with backend killed, no crash, all events get conservative routes with degraded flag; recovery test passes.
- Commit: `feat(core): failure injection and graceful degradation`

**Step 29 · Dual skill packaging (absorbs old Step 22)**
- Ship BOTH: an OpenClaw skill (per old §4.9) and a Claude Code skill. Add a `chief lite` mode: judgment-only (stages 1–3 + routing, no learner, no delivery daemon) so the skill form works standalone with minimal setup.
- Accept: both SKILL.md files lint clean; documented manual test transcript for each host.
- Commit: `feat(skills): claude-code and openclaw skill packaging`

**Step 30 · Upstream integration examples**
- `examples/integrations/`: two runnable examples showing the ecosystem position "noisy upstream agents → Chief as the judgment layer": (a) a stock-analysis-bot style feed (daily_stock_analysis-like, fixture-driven), (b) a generic webhook template any agent can copy.
- Each: one runnable script + a README section explaining the flow end-to-end.
- Accept: both scripts run end-to-end on fixture data producing visible Decisions.
- Commit: `docs(examples): upstream source integrations`

**Step 31 · README v2 — quantified first screen**
- Rewrite README: first screen leads with NUMBERS generated from real eval/demo output (interception rate, interrupts/day, % events reaching LLM, cache hit rate, judgment cost) — include a script that regenerates every number; then demo GIF placeholder, 60s quickstart.
- Promote "explainable judgment" to a first-class selling point (reason + components + `chief trace` for every decision). Keep the kill-all-clear section. Add the skills + integrations sections.
- Accept: every number in README is reproducible via `make readme-metrics`.
- Commit: `docs(readme): quantified value proposition`

### Phase 6 — Product Surface (v3.2 amendment, Steps 32–36)

> Owner directive (2026-07-06): as an open-source project the concept is
> clear; as a product for ordinary people three things are missing — a real
> UI, out-of-the-box sources, and a natural feedback mechanism. §13 revised
> accordingly (local-only console; connectors for ingest).

**Step 32 · Natural feedback — "should/shouldn't have interrupted me"**
- Two first-class signals: `should_interrupt` (this deserved my attention) and `should_not_interrupt` (this didn't). Learner effects stronger than passive signals; wired through the existing feedback table, MCP `feedback` tool, webhook `POST /v1/feedback`, and Telegram buttons.
- Accept: simulated feedback measurably moves the topic's future score in the right direction on both signals; HTTP + MCP paths covered by tests.
- Commit: `feat(learner): natural feedback signals`

**Step 33 · Local web console**
- Served by `chief run` (and standalone `chief ui`) on 127.0.0.1, token-gated, zero build toolchain (one static HTML+JS file shipped in the wheel). Views: today (digest queue + recent decisions with reason/score/cost), history (searchable decisions, per-event trace), rules (POLICY.md view/edit), tasks (pending dispatch approve/reject), sources (connector status), and 👍/👎 natural-feedback buttons on every decision.
- Accept: endpoint tests for every /api route (auth incl. 401); UI file lints as valid HTML; POLICY.md edits from the UI take effect on the next decision; approve/reject transitions a pending task.
- Commit: `feat(ui): local web console`

**Step 34 · Connector framework + Composio**
- `ingest/connectors/` registry (name → adapter). First adapter: **Composio** — HMAC-verified inbound webhook (`POST /v1/connectors/composio`, v3 envelope: metadata.trigger_slug + data), trigger_slug → topic mapping (GitHub/Gmail/Slack families), summary extraction with graceful fallback. Registry leaves documented slots for future channels (zapier, n8n, MCP-push).
- Accept: signature verification rejects tampered payloads; GitHub/Gmail/Slack trigger fixtures produce well-formed Events routed by the real pipeline; unknown slugs still ingest with a generic topic.
- Commit: `feat(ingest): connector framework with composio adapter`

**Step 35 · One-click connect**
- `chief connect <source>` CLI: writes config, prints the exact next actions (Composio dashboard steps / tokens), verifies inbound reachability where possible; `chief sources` lists connector status. The console's Sources view mirrors it.
- Accept: `chief connect composio --secret X` round-trips config and a signed test event; `chief sources` reflects it.
- Commit: `feat(cli): one-click source connection`

**Step 36 · Product docs + v0.3.0**
- README/zh gain the console screenshot placeholder + connectors section; CHANGELOG 0.3.0; version bump; tag v0.3.0 (release automation from v3.1 does the rest).
- Accept: release-check green from the wheel incl. `chief ui` assets; v0.3.0 release live with artifacts.
- Commit: `chore(release): v0.3.0 — product surface`

## 10. Config Sample (`~/.chief/config.toml`)
```toml
[llm]      backend = "deepseek"   model = "deepseek-v4-flash"   # or ollama/qwen3-4b
[delivery] channels = ["desktop","telegram"]   telegram_token = ""   chat_id = ""
[digest]   times = ["08:00","18:30"]
[quiet]    hours = "23:00-08:00"   whitelist = ["family","production_incident"]
[dispatch] claude_code_workdir = "~/work"   enabled = true
[context]  foreground_app = false            # privacy-sensitive, default OFF
```

## 11. Release Assets Checklist
1. README hero GIF: three events, three fates (#9, #16, #1) from demo mode.
2. 2-min video script: "the morning briefing" (record after Step 24).
3. Two deep-dive posts: the association chain (#5→#19 full trace), and dispatch verification ("done is a claim, not a proof").
4. docs/protocol.md as a standalone artifact — the protocol-definer posture.
5. ClawHub submission + awesome-list PRs.

## 12. Naming Note
Project name **Chief**. Before creating the repo, check availability of `agent-chief`, `chiefd`, `cortexd` on GitHub and PyPI; prefer the shortest available. All code, docs, comments, commit messages in English.

## 13. Explicitly OUT of scope (appearing in code = violation)

> Revised by the owner in v3.2 (2026-07-06). Two items were re-scoped, the
> rest remain absolute:
> - a **local web console** (served by `chief run` on 127.0.0.1 only, single
>   user, token-gated) is now IN scope — "Web UI" here always meant a hosted
>   multi-user product, which stays forbidden;
> - Slack/Gmail/GitHub **as ingest sources** (via connectors) are IN scope —
>   the ban below is on *delivery* through chat apps, which stands.

- Always-on microphone / screen-content understanding / geofencing (keep the provider interface ready; the hardware layer is a future premium provider)
- Hosted/multi-user UI, accounts, cloud sync, telemetry
- Arbitrary shell execution, homegrown agent executors
- Slack / Discord / WeChat **delivery** (ingest via connectors is allowed)
- Real-time association (at-ingest lookup + digest-time batch only)
- Heavy ML (EMA + threshold tuning is enough and stays explainable)
