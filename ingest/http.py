"""Implements SPEC §4.1: HTTP webhook ingest — POST /v1/events → Decision.

Default port 8787, simple bearer token. Example:

    curl -X POST http://localhost:8787/v1/events \\
      -H "Authorization: Bearer $CHIEF_TOKEN" -H "Content-Type: application/json" \\
      -d '{"source":"my-agent","topic":"dev.ci","summary":"CI failed on main"}'
"""

from fastapi import Depends, FastAPI, HTTPException, Request

from core.brain import Brain
from core.schema import Decision

DEFAULT_PORT = 8787


def create_app(brain: Brain, token: str, learner=None) -> FastAPI:
    from importlib.metadata import PackageNotFoundError
    from importlib.metadata import version as pkg_version

    try:
        v = pkg_version("agent-chief")
    except PackageNotFoundError:
        v = "0.0.0+source"
    app = FastAPI(title="chief ingest", version=v)

    def check_auth(request: Request) -> None:
        header = request.headers.get("authorization", "")
        if header != f"Bearer {token}":
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

    return app
