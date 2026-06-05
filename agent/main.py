"""CLI entry point for the device agent.

Usage:
    python -m agent.main pair --code ABCD-1234 --relay http://localhost:8000
    python -m agent.main start [--backend mock|ufo]
    python -m agent.main status
    python -m agent.main unpair
"""

from __future__ import annotations

import asyncio
import contextlib
from typing import Optional

import typer
import uvicorn
from rich.console import Console
from rich.panel import Panel

from .automation.base import DeviceAutomationBackend
from .automation.mock_backend import MockAutomationBackend
from .automation.ufo_backend import BackendUnavailableError, UfoAutomationBackend
from .config import AGENT_VERSION, AgentSettings
from .identity import PairingError, claim_pairing_code, ensure_local_identity
from .policy import DEFAULT_POLICY_YAML, load_policy
from .relay_client import RelayClient
from .storage import AgentStorage
from .task_runner import TaskRunner
from .ui.local_server import create_local_ui

app = typer.Typer(
    help="UFO Device Agent — pair this machine with a control plane and run AI-driven GUI tasks.",
    no_args_is_help=True,
)
console = Console()


def _make_backend(name: str) -> DeviceAutomationBackend:
    if name == "ufo":
        return UfoAutomationBackend()
    if name == "mock":
        return MockAutomationBackend()
    raise typer.BadParameter(f"unknown backend '{name}' (expected: mock, ufo)")


@app.command()
def pair(
    code: str = typer.Option(..., help="Pairing code from the control plane, e.g. ABCD-1234"),
    relay: str = typer.Option("http://localhost:8000", help="Control plane base URL"),
) -> None:
    """Claim a pairing code and store the device token locally."""
    settings = AgentSettings()
    storage = AgentStorage(settings.data_dir)
    state = storage.load_state()
    try:
        state = asyncio.run(
            claim_pairing_code(storage, state, code=code, relay_url=relay, device_name=settings.device_name)
        )
    except PairingError as exc:
        console.print(f"[red]Pairing failed:[/red] {exc}")
        raise typer.Exit(code=1)
    console.print(f"[green]Paired![/green] device_id={state.device_id}")
    console.print("Run [bold]python -m agent.main start[/bold] to bring this device online.")


@app.command()
def start(
    backend: Optional[str] = typer.Option(None, "--backend", help="Automation backend: mock (default) or ufo"),
) -> None:
    """Run the agent: relay connection + local UI + task runner."""
    settings = AgentSettings()
    backend_name = backend or settings.backend
    try:
        asyncio.run(_run(settings, backend_name))
    except BackendUnavailableError as exc:
        console.print(f"[red]{exc}[/red]")
        raise typer.Exit(code=1)
    except KeyboardInterrupt:
        pass


async def _run(settings: AgentSettings, backend_name: str) -> None:
    storage = AgentStorage(settings.data_dir)
    storage.ensure_policy_file(DEFAULT_POLICY_YAML)
    state = storage.load_state()
    ensure_local_identity(state, settings.device_name)
    storage.save_state(state)

    policy = load_policy(storage.policy_path)
    backend_impl = _make_backend(backend_name)
    runner = TaskRunner(backend_impl, policy, approval_timeout=settings.approval_timeout_seconds)
    relay = RelayClient(settings, storage, state, runner)
    runner.set_event_sender(relay.send)

    ui_app = create_local_ui(settings, storage, state, runner, relay)
    server = uvicorn.Server(
        uvicorn.Config(ui_app, host=settings.local_ui_host, port=settings.local_ui_port, log_level="warning")
    )

    ui_url = f"http://{settings.local_ui_host}:{settings.local_ui_port}"
    lines = [
        f"UFO Device Agent v{AGENT_VERSION}",
        f"device:  {state.device_name or settings.device_name}",
        f"backend: {backend_impl.name}",
        f"data:    {storage.data_dir}",
        f"policy:  {storage.policy_path}",
        f"UI:      {ui_url}",
    ]
    if state.paired:
        lines.append(f"paired:  yes -> {state.relay_url}")
    else:
        lines.append(f"paired:  [bold]NO[/bold] — pair at {ui_url} or run: python -m agent.main pair --code XXXX-XXXX")
    console.print(Panel("\n".join(lines), title="agent", border_style="cyan"))

    relay_task = asyncio.create_task(relay.run())
    try:
        await server.serve()  # returns on Ctrl+C
    finally:
        relay_task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await relay_task


@app.command()
def status() -> None:
    """Show stored identity / pairing state (token masked)."""
    settings = AgentSettings()
    storage = AgentStorage(settings.data_dir)
    state = storage.load_state()
    data = state.model_dump()
    for secret_field in ("device_token", "device_secret"):
        if data.get(secret_field):
            data[secret_field] = data[secret_field][:6] + "...(masked)"
    console.print_json(data=data)
    console.print(f"paired: {state.paired}   data dir: {storage.data_dir}")


@app.command()
def unpair() -> None:
    """Forget pairing (device token + relay URLs). Local identity is kept."""
    settings = AgentSettings()
    storage = AgentStorage(settings.data_dir)
    state = storage.load_state()
    state.device_id = None
    state.device_token = None
    state.relay_url = None
    state.relay_ws_url = None
    storage.save_state(state)
    console.print("[green]Unpaired.[/green] The control plane still holds its device record; remove it there too.")


def run() -> None:
    app()


if __name__ == "__main__":
    run()
