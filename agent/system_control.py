"""Privileged device controls: power off / restart / lock.

These are OS-level actions, not GUI automation, so they live outside the
automation backends. The TaskRunner routes ``system_*`` task types here, and
ALWAYS gates them behind an approval first (see task_runner). Like the
backends, this does real work or fails honestly — no simulation.

Power off / restart are scheduled with a short delay so the agent can flush
the ``task_completed`` event before the OS goes down; a pending shutdown can
be cancelled with ``shutdown /a`` during that window.
"""

from __future__ import annotations

import asyncio
import subprocess
import sys

from .models import TaskResult, TaskStatus, TaskType

CREATE_NO_WINDOW = 0x08000000
SHUTDOWN_DELAY_SECONDS = 5


def _run(args: list[str]) -> subprocess.CompletedProcess:
    return subprocess.run(args, capture_output=True, text=True, timeout=20, creationflags=CREATE_NO_WINDOW)


async def run_system_task(task_type: str, *, delay: int = SHUTDOWN_DELAY_SECONDS) -> TaskResult:
    """Execute a privileged system action. Returns a TaskResult; never raises."""
    if sys.platform != "win32":
        return TaskResult(
            status=TaskStatus.FAILED,
            summary=f"system action '{task_type}' is only implemented on Windows",
        )

    if task_type == TaskType.LOCK:
        args, ok_summary = (["rundll32.exe", "user32.dll,LockWorkStation"], "workstation locked")
    elif task_type == TaskType.POWER_OFF:
        args, ok_summary = (
            ["shutdown", "/s", "/t", str(delay), "/c", "Power off requested via ufo-device-agent"],
            f"shutdown scheduled in {delay}s (cancel with: shutdown /a)",
        )
    elif task_type == TaskType.RESTART:
        args, ok_summary = (
            ["shutdown", "/r", "/t", str(delay), "/c", "Restart requested via ufo-device-agent"],
            f"restart scheduled in {delay}s (cancel with: shutdown /a)",
        )
    else:
        return TaskResult(status=TaskStatus.FAILED, summary=f"unknown system task type: {task_type}")

    try:
        result = await asyncio.to_thread(_run, args)
    except Exception as exc:  # noqa: BLE001
        return TaskResult(status=TaskStatus.FAILED, summary=f"{type(exc).__name__}: {exc}")

    if result.returncode != 0:
        return TaskResult(status=TaskStatus.FAILED, summary=(result.stderr or result.stdout).strip()[:300])
    return TaskResult(status=TaskStatus.COMPLETED, summary=ok_summary)
