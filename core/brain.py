"""Implements SPEC §4.2/§4.4: brain-loop delivery — arrive with a plan.

When the judge flags an event dispatchable and it is heading to the user,
prep work runs FIRST and its verified result is merged into the message.
Dispatch timeout 10 min → deliver as-is, never block (SPEC §4.4).
"""

import asyncio
import logging
import time
from collections.abc import Callable
from datetime import UTC, datetime, timedelta

from core.policy import load_policy
from core.schema import Decision, DecisionTrace, Event, SceneState, StageTiming, Task
from core.scorer import SimilarityClassifier, find_mergeable, merge_events, score_and_route, stage1
from core.state import AuditLog, State
from delivery.base import DeliveryMessage
from dispatch.acceptance import AskFn, dispatch_and_verify
from dispatch.executor import Executor
from judge.base import Judge, JudgeContext, JudgeUsage
from judge.pricing import usd_cost

logger = logging.getLogger(__name__)

DISPATCH_TIMEOUT_SECONDS = 600.0  # 10 minutes
DEGRADED_KEY = "degraded"  # degradation marker in the meta kv table (Step 28)


async def load_degraded(state: State) -> dict | None:
    """Current degradation info ({'since','last_error'}) or None when healthy."""
    info = await state.get_meta(DEGRADED_KEY)
    return info if info and info.get("active") else None


class _StageClock:
    """Per-decision stage stopwatch feeding DecisionTrace (Step 26)."""

    def __init__(self):
        self.stages: list[StageTiming] = []
        self._t = time.perf_counter()

    def mark(self, stage: str, note: str = "") -> None:
        now = time.perf_counter()
        self.stages.append(StageTiming(stage=stage, ms=(now - self._t) * 1000, note=note))
        self._t = now


class Brain:
    """The triage→associate→decide loop for one incoming event (SPEC §4.2)."""

    def __init__(
        self,
        state: State,
        judge: Judge,
        *,
        policy_path,
        quiet_hours: str = "23:00-08:00",
        night_whitelist: list[str] | None = None,
        scene_engine=None,
        classifier: SimilarityClassifier | None = None,
        memory=None,
        inferrer=None,
        shadow=None,
        audit: AuditLog | None = None,
        user_profile: str = "",
        default_executor: str = "claude_code",
        embedder=None,
        actor: Callable | None = None,
        now_fn: Callable[[], datetime] = lambda: datetime.now(UTC),
        local_now_fn: Callable[[], datetime] | None = None,
        judge_timeout: float = 150.0,  # > HTTPJudge worst case (2 attempts x 60s) + slack
    ):
        self.state = state
        self.judge = judge
        self.policy_path = policy_path
        self.quiet_hours = quiet_hours
        self.night_whitelist = night_whitelist or ["family", "production_incident"]
        self.scene_engine = scene_engine
        self.classifier = classifier
        self.memory = memory
        self.inferrer = inferrer
        self.shadow = shadow
        self.audit = audit
        self.user_profile = user_profile
        self.default_executor = default_executor
        self.embedder = embedder
        self.actor = actor  # async (Event, Decision) -> None; delivery/dispatch side
        self.now_fn = now_fn
        self.local_now_fn = local_now_fn or (lambda: self.now_fn().astimezone())
        self.judge_timeout = judge_timeout
        self._degraded: bool | None = None  # None = unknown until first judgment
        self._last_error: str | None = None

    def _bill(self, backend: str, usage: JudgeUsage | None) -> float:
        if not usage:
            return 0.0
        return usd_cost(
            backend, usage.tokens_in, usage.tokens_out, usage.cached_tokens,
            model=getattr(self.judge, "model", None),
        )

    def _usage_trace(self, clock: _StageClock, backend: str, usage) -> DecisionTrace:
        return DecisionTrace(
            stages=clock.stages,
            tokens_in=usage.tokens_in if usage else 0,
            tokens_out=usage.tokens_out if usage else 0,
            cached_tokens=usage.cached_tokens if usage else 0,
            backend=backend,
        )

    def _scene(self, now: datetime) -> SceneState:
        if self.scene_engine:
            return self.scene_engine.current()
        return SceneState(scene="idle", confidence=0.4, signals={}, at=now)

    async def process(self, payload: dict | Event) -> Decision:
        from ingest.normalize import normalize

        now = self.now_fn()
        local_now = self.local_now_fn()
        clock = _StageClock()
        if isinstance(payload, Event):
            event = payload
        else:
            event = await normalize(payload, inferrer=self.inferrer, now=now)
        clock.mark("normalize")

        policy = load_policy(self.policy_path)
        scene = self._scene(local_now)
        recent_keys = await self.state.recent_dedup_keys(now - timedelta(hours=24))

        # Triage merge (SPEC §4.2 step 1): a same-topic near-duplicate within
        # 10 min folds into the earlier event; the earlier decision stands.
        if self.embedder:
            recent = await self.state.recent_events(now - timedelta(minutes=10))
            prior = find_mergeable(event, [e for e in recent if e.id != event.id],
                                   embedder=self.embedder)
            clock.mark("triage_merge", note="merged into prior" if prior else "no near-duplicate")
            if prior:
                merged = merge_events(prior, event)
                await self.state.save_event(merged)
                existing = await self.state.load_decision(prior.id)
                if existing:
                    # the prior decision (and its trace) stands for the merged event
                    return existing.model_copy(
                        update={"reason": existing.reason + "; merged near-duplicate"}
                    )

        hit = stage1(
            event,
            now=local_now,
            policy=policy,
            quiet_hours=self.quiet_hours,
            night_whitelist=self.night_whitelist,
            recent_dedup_keys=recent_keys,
        )
        if hit:
            clock.mark("stage1", note=f"rule {hit.rule} fired")
            decision = Decision(
                event_id=event.id,
                route=hit.route,  # type: ignore[arg-type]
                scene=scene.scene,
                scene_confidence=scene.confidence,
                cost=0.0,
                matched_rules=[hit.rule],
                reason=hit.reason,
                stage=1,
                trace=DecisionTrace(stages=clock.stages),
            )
        else:
            clock.mark("stage1", note="no hard rule fired")
            decision = await self._stage2_or_judge(event, scene, policy, now, clock)

        if self.shadow:
            route, annotation = await self.shadow.apply(decision, now=now)
            if annotation:
                decision = decision.model_copy(
                    update={"route": route, "reason": f"{decision.reason}; {annotation}"}
                )

        await self.state.save_event(event)
        await self.state.save_decision(decision)
        if self.actor:
            asyncio.ensure_future(self._act_safely(event, decision))
        if self.audit:
            self.audit.write(
                {
                    "at": now.isoformat(),
                    "event_id": event.id,
                    "route": decision.route,
                    "stage": decision.stage,
                    "score": decision.score,
                    "scene": decision.scene,
                    "reason": decision.reason,
                    "cost": decision.cost,
                    "prompt_version": decision.trace.prompt_version if decision.trace else None,
                    "degraded": decision.degraded,
                }
            )
        return decision

    async def _act_safely(self, event: Event, decision: Decision) -> None:
        try:
            await self.actor(event, decision)
        except Exception:
            logger.exception("actor failed for %s", event.id)

    async def _stage2_or_judge(
        self, event: Event, scene: SceneState, policy, now: datetime, clock: _StageClock
    ) -> Decision:
        if self.classifier:
            verdict = self.classifier.classify(event.summary)
            clock.mark("stage2", note=f"classifier says {verdict.action}")
            if verdict.action == "drop":
                return Decision(
                    event_id=event.id,
                    route="drop",
                    scene=scene.scene,
                    scene_confidence=scene.confidence,
                    cost=0.0,
                    reason=verdict.reason,
                    stage=2,
                    trace=DecisionTrace(stages=clock.stages),
                )
            if verdict.action == "route":
                return Decision(
                    event_id=event.id,
                    route=verdict.route,  # type: ignore[arg-type]
                    scene=scene.scene,
                    scene_confidence=scene.confidence,
                    cost=0.0,
                    reason=verdict.reason,
                    stage=2,
                    trace=DecisionTrace(stages=clock.stages),
                )

        memory_hits = []
        if self.memory:
            memory_hits = await self.memory.associate(event.summary, now=now)
        clock.mark("associate", note=f"{len(memory_hits)} memory hits")

        context = JudgeContext(
            user_profile=self.user_profile,
            associated_memory=[m.text for m in memory_hits],
            scene=scene.scene,
            scene_confidence=scene.confidence,
        )
        backend = getattr(self.judge, "name", "unknown")
        try:
            result = await asyncio.wait_for(
                self.judge.judge(event, context), self.judge_timeout
            )
        except Exception as exc:  # malformed output, timeout, backend down — never crash
            logger.warning("judge %s unavailable (%s); degrading to rules-only", backend, exc)
            last_error = f"{type(exc).__name__}: {exc}"[:200]
            if self._degraded is not True or last_error != self._last_error:
                # transition or changed failure mode: refresh the marker, but
                # preserve `since` from any still-active record (incl. one
                # written before a daemon restart mid-outage)
                current = await load_degraded(self.state)
                await self.state.set_meta(
                    DEGRADED_KEY,
                    {
                        "active": True,
                        "since": current["since"] if current else now.isoformat(),
                        "last_error": last_error,
                    },
                )
                self._degraded, self._last_error = True, last_error
            clock.mark("judge", note=f"FAILED: {type(exc).__name__}")
            # retries that failed were still paid for — bill them (JudgeError.usage)
            usage = getattr(exc, "usage", None)
            return Decision(
                event_id=event.id,
                route="digest",  # conservative: never interrupt, never drop, while blind
                scene=scene.scene,
                scene_confidence=scene.confidence,
                cost=self._bill(backend, usage),
                reason=f"judge unavailable ({type(exc).__name__}); "
                "conservative rules-only routing to digest",
                stage=3,
                degraded=True,
                trace=self._usage_trace(clock, backend, usage),
            )
        if self._degraded is not False:  # recovery (or first success): clear marker once
            await self.state.set_meta(DEGRADED_KEY, {"active": False})
            self._degraded = False
        clock.mark("judge", note=f"backend {backend}")
        weights = await self.state.get_topic_weights(event.topic)
        from core.learner import load_threshold_adjust

        route, score, comps, reason = score_and_route(
            result,
            scene,
            topic_weights=weights,
            threshold_overrides=policy.scene_thresholds,
            threshold_adjust=await load_threshold_adjust(self.state),
            memory_hit=bool(memory_hits),
        )
        clock.mark("route", note=f"routed {route}")
        if route == "curate" and result.memorize and self.memory:
            await self.memory.curate(
                result.memorize, topic=event.topic, origin_event_id=event.id, now=now
            )

        task_id = None
        if route == "dispatch" and result.dispatch_goal:
            task = Task(
                id=f"task_{event.id}",
                origin_event_id=event.id,
                goal=result.dispatch_goal,
                executor=self.default_executor,  # type: ignore[arg-type]
                acceptance=f"Result addresses the goal: {result.dispatch_goal}",
            )
            await self.state.save_task(task)
            task_id = task.id

        from judge import prompts

        usage = result.usage
        cost = self._bill(backend, usage)
        # only judges that render prompts (declare prompt_version) get stamped;
        # None on such a judge means "the active version" (fixtures stay None)
        _missing = object()
        declared = getattr(self.judge, "prompt_version", _missing)
        version = None if declared is _missing else (declared or prompts.PROMPT_VERSION)
        trace = self._usage_trace(clock, backend, usage)
        trace.prompt_version = version
        return Decision(
            event_id=event.id,
            route=route,  # type: ignore[arg-type]
            score=score,
            components=comps,
            scene=scene.scene,
            scene_confidence=scene.confidence,
            cost=cost,
            reason=reason,
            stage=3,
            dispatch_task_id=task_id,
            trace=trace,
        )


async def judge_once(payload: dict, config: dict | None = None) -> Decision:
    """One-shot judgment against an in-memory state (SPEC v3.1 Step 29).

    The single implementation behind `chief lite` and the integration
    examples: stages 1-3 + routing, no learner, no delivery daemon, no
    persistence. Honors [llm] and [quiet] from config so results match the
    resident daemon; with no backend configured, Step 28 degradation keeps it
    conservative (rules fire, the rest goes to digest with degraded=true).
    """
    from core.config import load_config, policy_path
    from judge.factory import make_judge

    cfg = config if config is not None else load_config()
    judge = make_judge(cfg.get("llm", {}))
    quiet = cfg.get("quiet", {})
    async with State.open(":memory:") as state:
        brain = Brain(
            state,
            judge,
            policy_path=policy_path(),
            quiet_hours=quiet.get("hours", "23:00-08:00"),
            night_whitelist=quiet.get("whitelist"),
        )
        return await brain.process(payload)


async def prepare_delivery(
    state: State,
    event: Event,
    *,
    goal: str,
    acceptance: str,
    executor: Executor,
    ask: AskFn | None = None,
    timeout: float = DISPATCH_TIMEOUT_SECONDS,
) -> tuple[DeliveryMessage, Task]:
    """Dispatch prep work, then build the delivery message with the plan merged in.

    Three outcomes: verified plan attached; timeout → original message as-is;
    dispatch rejected → the ask-the-human text rides along as the plan.
    """
    task = Task(
        id=f"task_{event.id}",
        origin_event_id=event.id,
        goal=goal,
        executor=executor.name,  # type: ignore[arg-type]
        acceptance=acceptance,
    )
    msg = DeliveryMessage(summary=event.summary, event_id=event.id, topic=event.topic)
    try:
        task, ask_human = await asyncio.wait_for(
            dispatch_and_verify(state, task, executor, ask=ask), timeout
        )
        if task.status == "done":
            msg.plan = task.result_summary
        elif ask_human:
            msg.plan = ask_human
    except TimeoutError:
        logger.warning(
            "dispatch for %s exceeded %.0fs; delivering as-is (never block)", event.id, timeout
        )
    return msg, task
