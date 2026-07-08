"""Implements SPEC §4.1: HTTP webhook ingest — POST /v1/events → Decision.

Default port 8787, simple bearer token. Example:

    curl -X POST http://localhost:8787/v1/events \\
      -H "Authorization: Bearer $CHIEF_TOKEN" -H "Content-Type: application/json" \\
      -d '{"source":"my-agent","topic":"dev.ci","summary":"CI failed on main"}'
"""

import hmac

from fastapi import Depends, FastAPI, HTTPException, Request

from core.brain import Brain
from core.schema import Decision

DEFAULT_PORT = 8787
MAX_WEBHOOK_BYTES = 1 << 20  # 1 MiB — reject oversized bodies before buffering


def create_app(
    brain: Brain, token: str, learner=None, executor_config: dict | None = None,
    connectors: dict | None = None,
) -> FastAPI:
    from importlib.metadata import PackageNotFoundError
    from importlib.metadata import version as pkg_version

    try:
        v = pkg_version("agent-chief")
    except PackageNotFoundError:
        v = "0.0.0+source"
    app = FastAPI(title="chief ingest", version=v)

    def check_auth(request: Request) -> None:
        header = request.headers.get("authorization", "")
        if not hmac.compare_digest(header, f"Bearer {token}"):  # constant-time
            raise HTTPException(status_code=401, detail="bad bearer token")

    @app.post("/v1/events", response_model=Decision)
    async def ingest_event(payload: dict, _: None = Depends(check_auth)) -> Decision:
        return await brain.process(payload)

    @app.post("/v1/feedback")
    async def submit_feedback(payload: dict, _: None = Depends(check_auth)) -> dict:
        """Natural feedback (SPEC v3.2 Step 32): should/shouldn't-interrupt etc."""
        from datetime import UTC, datetime

        from core.learner import KNOWN_SIGNALS

        event_id, signal = payload.get("event_id"), payload.get("signal")
        if not event_id or signal not in KNOWN_SIGNALS:
            raise HTTPException(status_code=422, detail="need event_id and a known signal")
        now = datetime.now(UTC)
        event = await brain.state.load_event(event_id)
        decision = await brain.state.load_decision(event_id)
        if learner and event and decision:
            await learner.record(event, decision, signal, at=now)  # saves the row too
            return {"ok": True, "learned": True}
        await brain.state.save_feedback(event_id, signal, now)
        return {"ok": True, "learned": False}

    # --- connectors (SPEC v3.2 Step 34): signed pushes from composio.dev ---

    @app.post("/v1/connectors/composio", response_model=Decision)
    async def composio_webhook(request: Request) -> Decision:
        from ingest.connectors.composio import (
            payload_to_event,
            timestamp_fresh,
            verify_signature,
        )

        secret = (connectors or {}).get("composio", {}).get("webhook_secret")
        if not secret:
            raise HTTPException(
                status_code=503,
                detail="composio connector not configured — run: chief connect composio",
            )
        # cap the body before buffering it all (endpoint is tunnel-exposed)
        declared = request.headers.get("content-length")
        if declared and declared.isdigit() and int(declared) > MAX_WEBHOOK_BYTES:
            raise HTTPException(status_code=413, detail="payload too large")
        body = await request.body()
        if len(body) > MAX_WEBHOOK_BYTES:
            raise HTTPException(status_code=413, detail="payload too large")
        ok = verify_signature(
            secret,
            request.headers.get("webhook-id", ""),
            request.headers.get("webhook-timestamp", ""),
            body,
            request.headers.get("webhook-signature", ""),
        )
        if not ok:
            raise HTTPException(status_code=401, detail="bad webhook signature")
        if not timestamp_fresh(request.headers.get("webhook-timestamp", "")):
            raise HTTPException(status_code=401, detail="stale webhook (replay?)")
        envelope = await request.json()
        return await brain.process(payload_to_event(envelope))

    # --- local web console (SPEC v3.2 Step 33; 127.0.0.1 only, token-gated) ---

    @app.get("/ui")
    async def console_page():
        from fastapi.responses import HTMLResponse

        from ui import CONSOLE_HTML_PATH

        return HTMLResponse(CONSOLE_HTML_PATH.read_text(encoding="utf-8"))

    @app.get("/api/overview")
    async def overview(_: None = Depends(check_auth)) -> dict:
        from datetime import timedelta

        from core.brain import load_degraded
        from core.learner import ShadowMode

        # window off the brain's clock, not wall-clock, so the 24h view is
        # consistent with the timestamps the pipeline stamped on decisions
        now = brain.now_fn()
        since = now - timedelta(hours=24)
        stats = await brain.state.decision_stats(since=since)
        stats["llm_share"] = stats["judged"] / stats["total"] if stats["total"] else 0.0
        return {
            "counts": await brain.state.route_counts(since=since),
            "stats": stats,
            "degraded": await load_degraded(brain.state),
            "shadow": await ShadowMode(brain.state).active(now),
        }

    @app.get("/api/decisions")
    async def decisions(limit: int = 50, q: str = "", _: None = Depends(check_auth)):
        rows = await brain.state.recent_decisions(limit=limit, q=q or None)
        return [
            {"event": e.model_dump(mode="json"), "decision": d.model_dump(mode="json")}
            for e, d in rows
        ]

    @app.get("/api/digest")
    async def digest_queue(_: None = Depends(check_auth)):
        from datetime import timedelta

        rows = await brain.state.digest_pool(brain.now_fn() - timedelta(hours=24))
        return [
            {"event": e.model_dump(mode="json"), "decision": d.model_dump(mode="json")}
            for e, d in rows
        ]

    @app.get("/api/policy")
    async def get_policy(_: None = Depends(check_auth)) -> dict:
        path = brain.policy_path
        return {"text": path.read_text(encoding="utf-8") if path.exists() else ""}

    @app.put("/api/policy")
    async def put_policy(payload: dict, _: None = Depends(check_auth)) -> dict:
        text = payload.get("text")
        if text is None:
            raise HTTPException(status_code=422, detail="need text")
        brain.policy_path.parent.mkdir(parents=True, exist_ok=True)
        brain.policy_path.write_text(text, encoding="utf-8")
        return {"ok": True}  # brain reloads POLICY.md per decision — live now

    @app.get("/api/tasks")
    async def list_tasks(_: None = Depends(check_auth)):
        rows = await brain.state.list_tasks()
        return [t.model_dump(mode="json") for t in rows]

    @app.post("/api/tasks/{task_id}")
    async def act_on_task(task_id: str, payload: dict, _: None = Depends(check_auth)) -> dict:
        task = await brain.state.load_task(task_id)
        if not task:
            raise HTTPException(status_code=404, detail="no such task")
        action = payload.get("action")
        if action == "reject":
            task.status = "rejected"
            await brain.state.save_task(task)
            return {"ok": True, "status": task.status}
        if action == "approve":
            from dispatch.acceptance import dispatch_and_verify
            from dispatch.executor import make_executor

            try:
                task_exec = make_executor(task.executor, executor_config or {})
            except ValueError:
                raise HTTPException(  # noqa: B904
                    status_code=409, detail=f"no executor for {task.executor!r}")
            task, _ask = await dispatch_and_verify(brain.state, task, task_exec)
            return {"ok": True, "status": task.status}
        raise HTTPException(status_code=422, detail="action must be approve or reject")

    @app.get("/api/sources")
    async def sources(_: None = Depends(check_auth)):
        from ingest.connectors import connector_status

        return connector_status()

    @app.get("/api/learning")
    async def learning(_: None = Depends(check_auth)):
        """What Chief has learned from feedback: per-topic weight drift from the
        0.20 default, plus the feedback tally that shaped it."""
        from core.scorer import DEFAULT_WEIGHTS, DIMS

        default = DEFAULT_WEIGHTS["urgency"]
        rows = []
        for topic, w in await brain.state.all_topic_weights():
            avg = sum(w.get(d, default) for d in DIMS) / len(DIMS)
            rows.append({
                "topic": topic,
                "weight": round(avg, 3),
                "drift": round(avg - default, 3),  # + = more likely to interrupt
                "urgency": round(w.get("urgency", default), 3),
            })
        rows.sort(key=lambda r: r["drift"], reverse=True)
        return {
            "default": default,
            "topics": rows,
            "signals": {
                s: await brain.state.count_feedback(signal=s)
                for s in ("should_interrupt", "should_not_interrupt",
                          "acted", "dismissed_fast", "muted")
            },
        }

    return app
