"""Outbound WebSocket connection to the control plane relay.

The device only ever dials OUT (ws/wss). No inbound ports, no RDP, no VPN.
Reconnects with exponential backoff; if the device is not paired yet, it idles
until pairing state appears (the local UI can pair while the agent runs).
"""

from __future__ import annotations

import asyncio
import json
from typing import Any

import websockets
from rich.console import Console

from .config import AGENT_VERSION, AgentSettings
from .models import DeviceMsg, RelayMsg, Task
from .storage import AgentState, AgentStorage
from .task_runner import TaskRunner

console = Console()

MAX_FRAME_BYTES = 10 * 1024 * 1024  # allow screenshots


class RelayClient:
    def __init__(
        self,
        settings: AgentSettings,
        storage: AgentStorage,
        state: AgentState,
        runner: TaskRunner,
    ) -> None:
        self.settings = settings
        self.storage = storage
        self.state = state  # shared, mutated in place when pairing happens
        self.runner = runner
        self.connected = False
        self._ws: websockets.WebSocketClientProtocol | None = None

    # --- sending -------------------------------------------------------------

    async def send(self, type_: str, payload: dict[str, Any]) -> None:
        ws = self._ws
        if ws is None:
            return  # offline; events are still in runner.recent_logs
        try:
            await ws.send(json.dumps({"type": type_, "payload": payload}, default=str))
        except Exception as exc:
            console.log(f"[yellow]relay send failed: {exc}[/yellow]")

    async def send_status(self) -> None:
        await self.send(
            DeviceMsg.STATUS,
            {
                "device_name": self.state.device_name or self.settings.device_name,
                "agent_version": AGENT_VERSION,
                **self.runner.status_snapshot(),
            },
        )

    # --- connection loop --------------------------------------------------------

    async def run(self) -> None:
        backoff = self.settings.reconnect_min_seconds
        while True:
            if not self.state.paired:
                # Pairing may have happened out-of-process (CLI `pair` while the
                # agent runs) — pick it up from disk without a restart.
                fresh = self.storage.load_state()
                if fresh.paired:
                    for field, value in fresh.model_dump().items():
                        setattr(self.state, field, value)
                    console.log("pairing detected on disk; connecting")
                else:
                    await asyncio.sleep(2.0)
                    continue

            url = f"{self.state.relay_ws_url}?token={self.state.device_token}"
            try:
                async with websockets.connect(url, max_size=MAX_FRAME_BYTES) as ws:
                    self._ws = ws
                    self.connected = True
                    backoff = self.settings.reconnect_min_seconds
                    console.log(f"[green]connected to relay:[/green] {self.state.relay_ws_url}")
                    await self.send(
                        DeviceMsg.HELLO,
                        {
                            "device_name": self.state.device_name or self.settings.device_name,
                            "agent_version": AGENT_VERSION,
                            "backend": self.runner.backend.name,
                        },
                    )
                    await self.send_status()
                    heartbeat = asyncio.create_task(self._heartbeat())
                    try:
                        async for raw in ws:
                            await self._handle_raw(raw)
                    finally:
                        heartbeat.cancel()
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                console.log(f"[yellow]relay connection error: {exc}[/yellow]")
            finally:
                self._ws = None
                self.connected = False

            console.log(f"reconnecting in {backoff:.0f}s ...")
            await asyncio.sleep(backoff)
            backoff = min(backoff * 2, self.settings.reconnect_max_seconds)

    async def _heartbeat(self) -> None:
        try:
            while True:
                await asyncio.sleep(self.settings.heartbeat_seconds)
                await self.send_status()
        except asyncio.CancelledError:
            pass

    # --- inbound message handling ---------------------------------------------------

    async def _handle_raw(self, raw: str | bytes) -> None:
        try:
            msg = json.loads(raw)
        except (json.JSONDecodeError, TypeError):
            console.log("[yellow]ignoring non-JSON relay frame[/yellow]")
            return

        mtype = msg.get("type")
        payload = msg.get("payload") or {}

        if mtype == RelayMsg.RUN_TASK:
            try:
                task = Task.model_validate(payload)
            except Exception as exc:
                console.log(f"[yellow]invalid run_task payload: {exc}[/yellow]")
                return
            # Fire and forget: the runner serializes tasks internally.
            asyncio.create_task(self.runner.run_task(task))

        elif mtype == RelayMsg.OBSERVE_SCREEN:
            asyncio.create_task(self._observe())

        elif mtype == RelayMsg.APPROVE_ACTION:
            self.runner.resolve_approval(str(payload.get("task_id", "")), True)

        elif mtype == RelayMsg.DENY_ACTION:
            self.runner.resolve_approval(str(payload.get("task_id", "")), False)

        elif mtype == RelayMsg.PAUSE:
            self.runner.pause()
            await self.send_status()

        elif mtype == RelayMsg.RESUME:
            self.runner.resume()
            await self.send_status()

        elif mtype == RelayMsg.UPDATE_POLICY:
            # TODO: validate payload["policy_yaml"], persist to storage.policy_path,
            # and hot-reload runner.policy. Deliberately not applied in MVP — a
            # remote party rewriting the local safety policy needs more thought
            # (signing? user confirmation in the local UI?).
            console.log("[yellow]update_policy received — not applied in MVP (see TODO)[/yellow]")

        else:
            console.log(f"[yellow]unknown relay message type: {mtype}[/yellow]")

    async def _observe(self) -> None:
        try:
            obs = await self.runner.backend.observe_screen()
        except Exception as exc:
            await self.send(DeviceMsg.TASK_LOG, {"task_id": "", "message": f"observe_screen failed: {exc}"})
            return
        await self.send(DeviceMsg.SCREENSHOT_AVAILABLE, obs.model_dump(mode="json"))
