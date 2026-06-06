"""End-to-end test of the vertical slice with the real `basic` backend.

Windows-only (the basic backend does real native actions). Spins up the
control plane and agent as subprocesses on free ports, then drives the full
flow over HTTP: create pairing code -> pair via the agent's local UI ->
device online -> run a real task (launches Notepad on the runner) -> logs
stream -> completed -> policy denial -> approval flow ending in an HONEST
failure (the basic backend refuses instructions it cannot actually perform).
"""

from __future__ import annotations

import json
import os
import socket
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

import pytest

pytestmark = pytest.mark.skipif(sys.platform != "win32", reason="basic backend does real Windows GUI actions")

REPO = Path(__file__).resolve().parents[1]
ADMIN = {"X-Admin-Token": "dev-admin-token"}


def free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def http(method: str, url: str, body: dict | None = None, headers: dict | None = None) -> dict | list:
    req = urllib.request.Request(url, method=method, headers={"Content-Type": "application/json", **(headers or {})})
    data = json.dumps(body).encode() if body is not None else None
    with urllib.request.urlopen(req, data=data, timeout=10) as resp:
        return json.loads(resp.read())


def wait_until(fn, timeout: float = 30.0, interval: float = 0.5):
    deadline = time.time() + timeout
    last_exc: Exception | None = None
    while time.time() < deadline:
        try:
            result = fn()
            if result:
                return result
        except Exception as exc:  # noqa: BLE001 — servers still starting
            last_exc = exc
        time.sleep(interval)
    raise AssertionError(f"condition not met within {timeout}s (last error: {last_exc})")


@pytest.fixture()
def stack(tmp_path: Path):
    cp_port, ui_port = free_port(), free_port()
    cp = subprocess.Popen(
        [sys.executable, "-m", "uvicorn", "control_plane.main:app", "--host", "127.0.0.1", "--port", str(cp_port)],
        cwd=REPO,
        env={**os.environ, "UFO_CP_DATA_DIR": str(tmp_path / "cp")},
    )
    agent = subprocess.Popen(
        [sys.executable, "-m", "agent.main", "start", "--backend", "basic"],
        cwd=REPO,
        env={
            **os.environ,
            "UFO_AGENT_DATA_DIR": str(tmp_path / "agent"),
            "UFO_AGENT_LOCAL_UI_PORT": str(ui_port),
            "UFO_AGENT_HEARTBEAT_SECONDS": "2",
            "UFO_AGENT_DISABLE_AUTOUPDATE": "1",  # source run is already inert; be explicit
        },
    )
    try:
        yield {"cp": f"http://127.0.0.1:{cp_port}", "ui": f"http://127.0.0.1:{ui_port}"}
    finally:
        for proc in (agent, cp):
            proc.terminate()
        for proc in (agent, cp):
            try:
                proc.wait(timeout=10)
            except subprocess.TimeoutExpired:
                proc.kill()
        subprocess.run(["taskkill", "/IM", "notepad.exe", "/F"], capture_output=True)  # clean up the real Notepad


def test_full_vertical_slice(stack: dict) -> None:
    cp, ui = stack["cp"], stack["ui"]

    # Both servers come up.
    wait_until(lambda: http("GET", f"{ui}/api/status")["backend"] == "basic")
    wait_until(lambda: http("GET", f"{cp}/api/admin/devices", headers=ADMIN) == [])

    # Pair: create code on the control plane, claim it via the agent local UI.
    code = http("POST", f"{cp}/api/admin/pairing", headers=ADMIN)["code"]
    assert http("POST", f"{ui}/api/pair", {"code": code, "relay_url": cp})["ok"]

    # Pairing codes are single-use: a second claim must fail.
    with pytest.raises(urllib.error.HTTPError):
        http("POST", f"{cp}/api/pairing/claim", {"code": code, "device_name": "imposter"})

    # Device comes online.
    device = wait_until(
        lambda: next((d for d in http("GET", f"{cp}/api/admin/devices", headers=ADMIN) if d["online"]), None)
    )
    dev_id = device["device_id"]

    def events() -> list:
        return http("GET", f"{cp}/api/admin/devices/{dev_id}/events?limit=200", headers=ADMIN)

    # Real task: actually launches Notepad on this machine.
    task = http("POST", f"{cp}/api/admin/devices/{dev_id}/tasks", {"instruction": "Open Notepad."}, headers=ADMIN)
    assert task["ok"]
    wait_until(lambda: any(e["type"] == "task_completed" and e["payload"]["task_id"] == task["task_id"]
                           for e in events()))

    # Policy: blocked app is denied without execution.
    http("POST", f"{cp}/api/admin/devices/{dev_id}/tasks", {"instruction": "Open the Banking app."}, headers=ADMIN)
    denied = wait_until(
        lambda: next((e for e in events() if e["type"] == "task_failed"
                      and "Banking" in e["payload"].get("summary", "")), None)
    )
    assert denied["payload"]["status"] == "denied"

    # Approval flow: risky task pauses; operator approves; then the backend
    # FAILS HONESTLY because it cannot actually perform an install.
    risky = http("POST", f"{cp}/api/admin/devices/{dev_id}/tasks", {"instruction": "Install the new printer driver."},
                 headers=ADMIN)
    approval = wait_until(
        lambda: next((e for e in events() if e["type"] == "approval_required"
                      and e["payload"]["task_id"] == risky["task_id"]), None)
    )
    http("POST", f"{cp}/api/admin/devices/{dev_id}/approve", {"task_id": approval["payload"]["task_id"]},
         headers=ADMIN)
    failed = wait_until(
        lambda: next((e for e in events() if e["type"] == "task_failed"
                      and e["payload"]["task_id"] == risky["task_id"]), None)
    )
    assert failed["payload"]["status"] == "failed"
    assert "could not parse" in failed["payload"]["summary"]

    # Privileged system task: power_off is ALWAYS approval-gated. DENY it here
    # (approving would shut down the CI runner). Verifies the gate, not the act.
    power = http("POST", f"{cp}/api/admin/devices/{dev_id}/tasks",
                 {"type": "power_off", "instruction": "Power off device"}, headers=ADMIN)
    p_appr = wait_until(
        lambda: next((e for e in events() if e["type"] == "approval_required"
                      and e["payload"]["task_id"] == power["task_id"]), None)
    )
    assert "power_off" in p_appr["payload"]["reason"]
    http("POST", f"{cp}/api/admin/devices/{dev_id}/deny", {"task_id": power["task_id"]}, headers=ADMIN)
    p_denied = wait_until(
        lambda: next((e for e in events() if e["type"] == "task_failed"
                      and e["payload"]["task_id"] == power["task_id"]), None)
    )
    assert p_denied["payload"]["status"] == "denied"

    # Delete the device: it disappears from the registry and its history 404s.
    assert http("DELETE", f"{cp}/api/admin/devices/{dev_id}", headers=ADMIN)["ok"]
    assert all(d["device_id"] != dev_id for d in http("GET", f"{cp}/api/admin/devices", headers=ADMIN))
    with pytest.raises(urllib.error.HTTPError):
        http("GET", f"{cp}/api/admin/devices/{dev_id}/events", headers=ADMIN)
    # Deleting again is a clean 404.
    with pytest.raises(urllib.error.HTTPError):
        http("DELETE", f"{cp}/api/admin/devices/{dev_id}", headers=ADMIN)
