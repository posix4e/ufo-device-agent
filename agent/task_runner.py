"""Task execution pipeline: policy check -> (approval) -> backend -> events.

TaskRunner is also the agent's shared runtime state (current task, pause flag,
recent logs, pending approvals) consumed by both the local UI and the relay
client. Tasks run serially (one at a time) in MVP.
"""

from __future__ import annotations

import asyncio
import json
from collections import deque
from typing import Any, Awaitable, Callable

from rich.console import Console

from .automation.base import DeviceAutomationBackend
from .models import DeviceMsg, Task, TaskResult, TaskStatus, utc_now
from .policy import Policy

EventSender = Callable[[str, dict[str, Any]], Awaitable[None]]

console = Console()


class PendingApproval:
    def __init__(self, task: Task, reason: str) -> None:
        self.task = task
        self.reason = reason
        self.future: asyncio.Future[bool] = asyncio.get_running_loop().create_future()


class TaskRunner:
    def __init__(
        self,
        backend: DeviceAutomationBackend,
        policy: Policy,
        *,
        approval_timeout: float = 600.0,
    ) -> None:
        self.backend = backend
        self.policy = policy
        self.approval_timeout = approval_timeout

        self.paused = False
        self._resume_event = asyncio.Event()
        self._resume_event.set()
        self._serial = asyncio.Lock()  # MVP: one task at a time

        self.current_task: Task | None = None
        self.last_result: TaskResult | None = None
        self.recent_logs: deque[dict[str, Any]] = deque(maxlen=300)
        self.pending_approvals: dict[str, PendingApproval] = {}

        self._send_event: EventSender | None = None
        backend.set_log_callback(self._on_backend_log)

    # --- wiring ----------------------------------------------------------------

    def set_event_sender(self, sender: EventSender) -> None:
        """Called by main once the relay client exists."""
        self._send_event = sender

    # --- event emission ----------------------------------------------------------

    async def emit(self, type_: str, payload: dict[str, Any]) -> None:
        """Record an event locally and forward it to the relay (if connected)."""
        safe_payload = {k: v for k, v in payload.items() if k != "screenshot_b64"}
        self.recent_logs.append({"ts": utc_now().isoformat(), "type": type_, "payload": safe_payload})
        console.log(f"[bold cyan]{type_}[/bold cyan] {json.dumps(safe_payload, default=str)[:200]}")
        if self._send_event is not None:
            try:
                await self._send_event(type_, payload)
            except Exception as exc:  # never let relay trouble kill a task
                console.log(f"[yellow]failed to forward event to relay: {exc}[/yellow]")

    async def _on_backend_log(self, message: str) -> None:
        task_id = self.current_task.task_id if self.current_task else ""
        await self.emit(DeviceMsg.TASK_LOG, {"task_id": task_id, "message": message})

    # --- pause / resume -----------------------------------------------------------

    def pause(self) -> None:
        self.paused = True
        self._resume_event.clear()

    def resume(self) -> None:
        self.paused = False
        self._resume_event.set()

    # --- approvals -----------------------------------------------------------------

    def resolve_approval(self, task_id: str, approved: bool) -> bool:
        """Resolve a pending approval (from local UI or relay). Returns False if unknown."""
        pa = self.pending_approvals.get(task_id)
        if pa is None or pa.future.done():
            return False
        pa.future.set_result(approved)
        return True

    async def _wait_for_approval(self, task: Task, reason: str) -> bool:
        pa = PendingApproval(task, reason)
        self.pending_approvals[task.task_id] = pa
        await self.emit(
            DeviceMsg.APPROVAL_REQUIRED,
            {"task_id": task.task_id, "instruction": task.instruction, "reason": reason},
        )
        try:
            return await asyncio.wait_for(asyncio.shield(pa.future), timeout=self.approval_timeout)
        except asyncio.TimeoutError:
            return False
        finally:
            self.pending_approvals.pop(task.task_id, None)

    # --- execution ------------------------------------------------------------------

    async def run_task(self, task: Task) -> TaskResult:
        async with self._serial:
            self.current_task = task
            try:
                result = await self._run_task_inner(task)
            finally:
                self.current_task = None
            self.last_result = result
            return result

    async def _run_task_inner(self, task: Task) -> TaskResult:
        decision = self.policy.evaluate(task.instruction)
        if decision.action == "deny":
            result = TaskResult(
                task_id=task.task_id,
                status=TaskStatus.DENIED,
                summary=f"Denied by policy: {decision.reason}",
            )
            await self.emit(DeviceMsg.TASK_FAILED, result.model_dump(mode="json"))
            return result

        await self.emit(
            DeviceMsg.TASK_STARTED,
            {"task_id": task.task_id, "instruction": task.instruction, "policy": decision.action},
        )

        if task.require_approval or decision.action == "require_approval":
            reason = decision.reason or "task was flagged require_approval"
            approved = await self._wait_for_approval(task, reason)
            if not approved:
                result = TaskResult(
                    task_id=task.task_id,
                    status=TaskStatus.DENIED,
                    summary=f"Not approved (reason it needed approval: {reason})",
                )
                await self.emit(DeviceMsg.TASK_FAILED, result.model_dump(mode="json"))
                return result
            await self.emit(DeviceMsg.TASK_LOG, {"task_id": task.task_id, "message": "Approval granted; continuing"})

        # Honor pause: block here until resumed.
        if self.paused:
            await self.emit(DeviceMsg.TASK_LOG, {"task_id": task.task_id, "message": "Agent paused; waiting for resume"})
        await self._resume_event.wait()

        try:
            result = await self.backend.run_instruction(task.instruction)
            result.task_id = task.task_id
        except Exception as exc:
            result = TaskResult(
                task_id=task.task_id,
                status=TaskStatus.FAILED,
                summary=f"{type(exc).__name__}: {exc}",
            )

        msg_type = DeviceMsg.TASK_COMPLETED if result.status == TaskStatus.COMPLETED else DeviceMsg.TASK_FAILED
        await self.emit(msg_type, result.model_dump(mode="json"))
        return result

    # --- status ----------------------------------------------------------------------

    def status_snapshot(self) -> dict[str, Any]:
        return {
            "backend": self.backend.name,
            "paused": self.paused,
            "current_task": self.current_task.model_dump(mode="json") if self.current_task else None,
            "last_result": self.last_result.model_dump(mode="json") if self.last_result else None,
            "pending_approvals": [
                {"task_id": pa.task.task_id, "instruction": pa.task.instruction, "reason": pa.reason}
                for pa in self.pending_approvals.values()
            ],
        }
