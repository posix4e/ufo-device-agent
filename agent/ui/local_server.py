"""Local web UI + status API for the device owner.

Loopback-only and unauthenticated by design for the MVP — anything that can
hit this API is already running as the local user. It exposes approve/deny,
so it must NEVER be bound to a non-loopback interface.

This UI is intentionally always available while the agent runs: visibility
into what the agent is doing is a core safety requirement (no stealth).
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException
from fastapi.responses import HTMLResponse
from pydantic import BaseModel

from ..config import AGENT_VERSION, AgentSettings
from ..identity import PairingError, claim_pairing_code
from ..relay_client import RelayClient
from ..storage import AgentState, AgentStorage
from ..task_runner import TaskRunner

TEMPLATE_PATH = Path(__file__).parent / "templates" / "index.html"


class PairRequest(BaseModel):
    code: str
    relay_url: str = "http://localhost:8000"


def create_local_ui(
    settings: AgentSettings,
    storage: AgentStorage,
    state: AgentState,
    runner: TaskRunner,
    relay: RelayClient,
) -> FastAPI:
    app = FastAPI(title="UFO Device Agent — Local UI", version=AGENT_VERSION)

    @app.get("/", response_class=HTMLResponse)
    async def index() -> str:
        return TEMPLATE_PATH.read_text(encoding="utf-8")

    @app.get("/api/status")
    async def status() -> dict[str, Any]:
        return {
            "agent_version": AGENT_VERSION,
            "device_name": state.device_name or settings.device_name,
            "device_id": state.device_id,
            "paired": state.paired,
            "online": relay.connected,
            "relay_url": state.relay_url,
            **runner.status_snapshot(),
        }

    @app.get("/api/logs")
    async def logs() -> list[dict[str, Any]]:
        return list(runner.recent_logs)

    @app.post("/api/pair")
    async def pair(req: PairRequest) -> dict[str, Any]:
        if state.paired:
            raise HTTPException(status_code=409, detail="already paired — unpair first")
        try:
            await claim_pairing_code(
                storage, state, code=req.code, relay_url=req.relay_url, device_name=settings.device_name
            )
        except PairingError as exc:
            raise HTTPException(status_code=400, detail=str(exc))
        # The relay client polls state.paired and connects on its own.
        return {"ok": True, "device_id": state.device_id}

    @app.post("/api/pause")
    async def pause() -> dict[str, Any]:
        runner.pause()
        await relay.send_status()
        return {"ok": True, "paused": True}

    @app.post("/api/resume")
    async def resume() -> dict[str, Any]:
        runner.resume()
        await relay.send_status()
        return {"ok": True, "paused": False}

    @app.post("/api/approvals/{task_id}/approve")
    async def approve(task_id: str) -> dict[str, Any]:
        if not runner.resolve_approval(task_id, True):
            raise HTTPException(status_code=404, detail="no pending approval with that task_id")
        return {"ok": True}

    @app.post("/api/approvals/{task_id}/deny")
    async def deny(task_id: str) -> dict[str, Any]:
        if not runner.resolve_approval(task_id, False):
            raise HTTPException(status_code=404, detail="no pending approval with that task_id")
        return {"ok": True}

    return app
