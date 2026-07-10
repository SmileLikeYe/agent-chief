"""Implements SPEC §2/§4.8: the resident process — one async event loop wiring
scene engine, brain, webhook, pollers, telegram feedback, and scheduled jobs."""

import asyncio
import logging
from datetime import UTC, datetime

from rich.console import Console

from context.infer import SceneEngine
from context.providers.clock import ClockProvider
from core.brain import Brain
from core.config import (
    audit_log_path,
    config_path,
    db_path,
    load_config,
    policy_path,
    user_md_path,
)
from core.embedding import make_embedder
from core.learner import Learner, ShadowMode
from core.scorer import SimilarityClassifier
from core.state import AuditLog, State
from judge.factory import make_judge
from memory.store import MemoryStore

logger = logging.getLogger(__name__)
console = Console()
REMOTE_JUDGES = {"deepseek", "anthropic", "openai"}


def judge_config_error(llm: dict) -> str | None:
    backend = llm.get("backend", "fixtures")
    if backend == "fixtures":
        return "fixtures is demo-only; run `chief init` and choose a real judge backend"
    if backend in REMOTE_JUDGES and not llm.get("api_key") and not llm.get("base_url"):
        return f"{backend} requires [llm].api_key; run `chief init` to configure it"
    if backend not in {*REMOTE_JUDGES, "ollama"}:
        return f"unknown judge backend {backend!r}; run `chief init` to choose one"
    return None


def make_actor(state: State, config: dict, channels: list):
    """The delivery/dispatch side of a Decision (SPEC §4.4/§4.5): interrupts are
    delivered scene-capped; dispatch runs first and arrives with a plan."""
    from core.brain import prepare_delivery
    from delivery.base import DeliveryMessage, deliver
    from dispatch.executor import make_executor

    dispatch_cfg = config.get("dispatch", {})

    async def act(event, decision) -> None:
        scene = decision.scene
        if decision.route == "interrupt":
            msg = DeliveryMessage(summary=event.summary, event_id=event.id, topic=event.topic)
            await deliver(msg, "ring", scene, channels)
        elif decision.route == "dispatch":
            task = (
                await state.load_task(decision.dispatch_task_id)
                if decision.dispatch_task_id
                else None
            )
            if task is None or not dispatch_cfg.get("enabled", True):
                msg = DeliveryMessage(
                    summary=event.summary, event_id=event.id, topic=event.topic
                )
                await deliver(msg, "silent", scene, channels)
                return
            executor = make_executor(task.executor, dispatch_cfg)
            msg, _task = await prepare_delivery(
                state,
                event,
                goal=task.goal,
                acceptance=task.acceptance,
                executor=executor,
            )
            await deliver(msg, "silent", scene, channels)
        # digest items wait for the scheduled digest; curate/drop need no action

    return act


def make_channels(delivery_cfg: dict) -> list:
    from delivery.desktop import DesktopChannel
    from delivery.terminal import TerminalChannel

    channels: list = [TerminalChannel()]
    if "desktop" in delivery_cfg.get("channels", []):
        channels.append(DesktopChannel())
    token = delivery_cfg.get("telegram_token")
    if token and delivery_cfg.get("chat_id"):
        from delivery.telegram import TelegramChannel

        channels.append(TelegramChannel(token=token, chat_id=str(delivery_cfg["chat_id"])))
    return channels


async def tick_jobs(
    state: State,
    memory: MemoryStore,
    policy_file,
    channels: list,
    digest_times: list[str],
    now: datetime,
    fired: set,
    *,
    wall_time: datetime | None = None,
) -> None:
    """One scheduler tick: digest at configured times, distillation+expiry at 03:00."""
    from datetime import timedelta

    from core.digest import build_digest, distill, render_digest
    from delivery.base import DeliveryMessage, deliver

    wall_time = wall_time or now
    hm, day = f"{wall_time:%H:%M}", f"{wall_time:%Y-%m-%d}"
    if hm in digest_times and (day, hm) not in fired:
        fired.add((day, hm))
        digest = await build_digest(state, memory, since=now - timedelta(hours=24), now=now)
        digest.at = wall_time
        msg = DeliveryMessage(
            summary=render_digest(digest), event_id=f"digest_{day}_{hm}",
            topic="chief.digest", buttons=False,
        )
        await deliver(msg, "desktop", "idle", channels)
    if hm == "03:00" and (day, "distill") not in fired:
        fired.add((day, "distill"))
        from core.learner import daily_threshold_tuning

        await distill(state, policy_file, now=now)
        await memory.expire(now=now)
        await daily_threshold_tuning(state, now=now)


async def scheduler_loop(state, memory, policy_file, channels, digest_times) -> None:
    fired: set = set()
    while True:
        now = datetime.now(UTC)
        await tick_jobs(
            state,
            memory,
            policy_file,
            channels,
            digest_times,
            now,
            fired,
            wall_time=now.astimezone(),
        )
        await asyncio.sleep(30)


async def run_resident(once: bool = False) -> None:
    config = load_config()
    if not config:
        console.print(f"no config at {config_path()} — run [bold]chief init[/bold] first")
        raise SystemExit(1)

    llm = config.get("llm", {})
    if error := judge_config_error(llm):
        console.print(f"[red]judge is not configured[/red]: {error}")
        raise SystemExit(2)
    quiet = config.get("quiet", {})
    ingest_cfg = config.get("ingest", {})
    delivery_cfg = config.get("delivery", {})

    async with State.open(db_path()) as state:
        embedder = make_embedder(config.get("memory", {}))
        classifier = SimilarityClassifier(embedder=embedder)
        memory = MemoryStore(state, embedder=embedder)
        shadow = ShadowMode(state)
        await shadow.ensure_started(datetime.now(UTC))
        learner = Learner(state, classifier=classifier)
        await learner.rebuild_classifier()

        channels = make_channels(delivery_cfg)
        def local_now_fn() -> datetime:
            return datetime.now().astimezone()

        brain = Brain(
            state,
            make_judge(llm),
            policy_path=policy_path(),
            quiet_hours=quiet.get("hours", "23:00-08:00"),
            night_whitelist=quiet.get("whitelist", ["family", "production_incident"]),
            scene_engine=SceneEngine(
                [ClockProvider(quiet.get("hours", "23:00-08:00"))],
                now_fn=local_now_fn,
            ),
            classifier=classifier,
            memory=memory,
            shadow=shadow,
            audit=AuditLog(audit_log_path()),
            embedder=embedder,
            actor=make_actor(state, config, channels),
            local_now_fn=local_now_fn,
            user_profile=(
                user_md_path().read_text(encoding="utf-8") if user_md_path().exists() else ""
            ),
        )

        tasks: list[asyncio.Task] = []
        if not once:
            tasks.extend(
                await _start_network(
                    brain, state, ingest_cfg, delivery_cfg, learner=learner,
                    executor_config=config.get("dispatch", {}),
                )
            )
            tasks.append(
                asyncio.ensure_future(
                    scheduler_loop(
                        state, memory, policy_path(), channels,
                        config.get("digest", {}).get("times", ["08:00", "18:30"]),
                    )
                )
            )

        console.print(
            f"✅ chief is up — judge={llm.get('backend', 'fixtures')} "
            f"webhook=:{ingest_cfg.get('webhook_port', 8787)} "
            f"shadow={'on' if await shadow.active(datetime.now(UTC)) else 'off'}"
        )
        if once:
            return
        try:
            await asyncio.gather(*tasks)
        except (KeyboardInterrupt, asyncio.CancelledError):
            for t in tasks:
                t.cancel()


async def run_console() -> None:
    """SPEC v3.2 Step 33: the console without pollers/scheduler/telegram —
    `chief ui` for people who don't run the resident daemon."""
    import uvicorn

    from ingest.http import create_app
    from judge.factory import make_judge

    config = load_config()
    ingest_cfg = config.get("ingest", {})
    async with State.open(db_path()) as state:
        embedder = make_embedder(config.get("memory", {}))
        learner = Learner(state, classifier=SimilarityClassifier(embedder=embedder))
        brain = Brain(
            state,
            make_judge(config.get("llm", {})),
            policy_path=policy_path(),
            embedder=embedder,
        )
        app = create_app(
            brain, token=ingest_cfg.get("webhook_token", "change-me"),
            learner=learner,
            executor_config=config.get("dispatch", {}),
            connectors=config.get("connectors", {}),
        )
        port = int(ingest_cfg.get("webhook_port", 8787))
        Console().print(f"🎩 console: [bold]http://127.0.0.1:{port}/ui[/bold]")
        cfg = uvicorn.Config(app, host="127.0.0.1", port=port, log_level="warning")
        await uvicorn.Server(cfg).serve()


async def _start_network(
    brain, state, ingest_cfg, delivery_cfg, learner=None, executor_config=None
) -> list[asyncio.Task]:
    import uvicorn

    from ingest.http import create_app
    from ingest.sources import github as gh_source
    from ingest.sources import rss as rss_source

    tasks = []
    app = create_app(
        brain, token=ingest_cfg.get("webhook_token", "change-me"),
        learner=learner, executor_config=executor_config,
        connectors=load_config().get("connectors", {}),
    )
    server = uvicorn.Server(
        uvicorn.Config(app, host="127.0.0.1",
                       port=int(ingest_cfg.get("webhook_port", 8787)), log_level="warning")
    )
    tasks.append(asyncio.ensure_future(server.serve()))

    if ingest_cfg.get("github"):
        tasks.append(asyncio.ensure_future(gh_source.make_poller(brain.process).run()))
    for url in ingest_cfg.get("rss_urls", []):
        tasks.append(asyncio.ensure_future(rss_source.make_poller(url, brain.process).run()))

    token = delivery_cfg.get("telegram_token")
    if token and delivery_cfg.get("chat_id"):
        from delivery.telegram import TelegramChannel

        channel = TelegramChannel(token=token, chat_id=str(delivery_cfg["chat_id"]))
        tasks.append(asyncio.ensure_future(channel.poll_callbacks(state, policy_path())))
    return tasks
