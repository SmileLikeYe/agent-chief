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


def create_app(brain: Brain, token: str) -> FastAPI:
    app = FastAPI(title="chief ingest", version="0.1.0")

    def check_auth(request: Request) -> None:
        header = request.headers.get("authorization", "")
        if header != f"Bearer {token}":
            raise HTTPException(status_code=401, detail="bad bearer token")

    @app.post("/v1/events", response_model=Decision)
    async def ingest_event(payload: dict, _: None = Depends(check_auth)) -> Decision:
        return await brain.process(payload)

    return app
