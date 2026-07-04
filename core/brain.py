"""Implements SPEC §4.2/§4.4: brain-loop delivery — arrive with a plan.

When the judge flags an event dispatchable and it is heading to the user,
prep work runs FIRST and its verified result is merged into the message.
Dispatch timeout 10 min → deliver as-is, never block (SPEC §4.4).
"""

import asyncio
import logging
from collections.abc import Callable
from datetime import UTC, datetime, timedelta

from core.policy import load_policy
from core.schema import Decision, Event, SceneState, Task
from core.scorer import SimilarityClassifier, find_mergeable, merge_events, score_and_route, stage1
from core.state import AuditLog, State
from delivery.base import DeliveryMessage
from dispatch.acceptance import AskFn, dispatch_and_verify
from dispatch.executor import Executor
from judge.base import Judge, JudgeContext

logger = logging.getLogger(__name__)

DISPATCH_TIMEOUT_SECONDS = 600.0  # 10 minutes


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

    def _scene(self, now: datetime) -> SceneState:
        if self.scene_engine:
            return self.scene_engine.current()
        return SceneState(scene="idle", confidence=0.4, signals={}, at=now)

    async def process(self, payload: dict | Event) -> Decision:
        from ingest.normalize import normalize

        now = self.now_fn()
        if isinstance(payload, Event):
            event = payload
        else:
            event = await normalize(payload, inferrer=self.inferrer, now=now)

        policy = load_policy(self.policy_path)
        scene = self._scene(now)
        recent_keys = await self.state.recent_dedup_keys(now - timedelta(hours=24))

        # Triage merge (SPEC §4.2 step 1): a same-topic near-duplicate within
        # 10 min folds into the earlier event; the earlier decision stands.
        if self.embedder:
            recent = await self.state.recent_events(now - timedelta(minutes=10))
            prior = find_mergeable(event, [e for e in recent if e.id != event.id],
                                   embedder=self.embedder)
            if prior:
                merged = merge_events(prior, event)
                await self.state.save_event(merged)
                existing = await self.state.load_decision(prior.id)
                if existing:
                    return existing.model_copy(
                        update={"reason": existing.reason + "; merged near-duplicate"}
                    )

        hit = stage1(
            event,
            now=now,
            policy=policy,
            quiet_hours=self.quiet_hours,
            night_whitelist=self.night_whitelist,
            recent_dedup_keys=recent_keys,
        )
        if hit:
            decision = Decision(
                event_id=event.id,
                route=hit.route,  # type: ignore[arg-type]
                scene=scene.scene,
                scene_confidence=scene.confidence,
                cost=0.0,
                matched_rules=[hit.rule],
                reason=hit.reason,
                stage=1,
            )
        else:
            decision = await self._stage2_or_judge(event, scene, policy, now)

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
                }
            )
        return decision

    async def _act_safely(self, event: Event, decision: Decision) -> None:
        try:
            await self.actor(event, decision)
        except Exception:
            logger.exception("actor failed for %s", event.id)

    async def _stage2_or_judge(
        self, event: Event, scene: SceneState, policy, now: datetime
    ) -> Decision:
        if self.classifier:
            verdict = self.classifier.classify(event.summary)
            if verdict.action == "drop":
                return Decision(
                    event_id=event.id,
                    route="drop",
                    scene=scene.scene,
                    scene_confidence=scene.confidence,
                    cost=0.0,
                    reason=verdict.reason,
                    stage=2,
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
                )

        memory_hits = []
        if self.memory:
            memory_hits = await self.memory.associate(event.summary, now=now)

        context = JudgeContext(
            user_profile=self.user_profile,
            associated_memory=[m.text for m in memory_hits],
            scene=scene.scene,
            scene_confidence=scene.confidence,
        )
        result = await self.judge.judge(event, context)
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

        return Decision(
            event_id=event.id,
            route=route,  # type: ignore[arg-type]
            score=score,
            components=comps,
            scene=scene.scene,
            scene_confidence=scene.confidence,
            cost=0.0,
            reason=reason,
            stage=3,
            dispatch_task_id=task_id,
        )


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
