"""Pydantic models and the WebSocket message protocol for the device agent.

Wire format
-----------
Every WebSocket frame is a JSON object: ``{"type": "<msg type>", "payload": {...}}``.

Device -> Relay message types (``DeviceMsg``):
    device_hello, device_status, task_started, task_log, task_completed,
    task_failed, approval_required, screenshot_available, update_failed

Relay -> Device message types (``RelayMsg``):
    run_task, observe_screen, approve_action, deny_action, pause, resume,
    update_policy, update_agent
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from enum import Enum
from typing import Any

from pydantic import BaseModel, Field


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def new_uuid() -> str:
    return str(uuid.uuid4())


# --- message type constants -------------------------------------------------


class DeviceMsg:
    """Messages the device sends to the relay."""

    HELLO = "device_hello"
    STATUS = "device_status"
    TASK_STARTED = "task_started"
    TASK_LOG = "task_log"
    TASK_COMPLETED = "task_completed"
    TASK_FAILED = "task_failed"
    APPROVAL_REQUIRED = "approval_required"
    SCREENSHOT_AVAILABLE = "screenshot_available"
    UPDATE_FAILED = "update_failed"


class RelayMsg:
    """Messages the relay sends to the device."""

    RUN_TASK = "run_task"
    OBSERVE_SCREEN = "observe_screen"
    APPROVE_ACTION = "approve_action"
    DENY_ACTION = "deny_action"
    PAUSE = "pause"
    RESUME = "resume"
    UPDATE_POLICY = "update_policy"
    UPDATE_AGENT = "update_agent"


class WsMessage(BaseModel):
    type: str
    payload: dict[str, Any] = Field(default_factory=dict)


# --- task / result models ----------------------------------------------------


class TaskType:
    """Task kinds. run_instruction goes to the GUI automation backend;
    the system_* kinds are privileged device controls (always approval-gated)
    handled outside the backend."""

    RUN_INSTRUCTION = "run_instruction"
    POWER_OFF = "power_off"
    RESTART = "restart"
    LOCK = "lock"


# Privileged, OS-level device actions — never silently executed.
SYSTEM_TASK_TYPES = frozenset({TaskType.POWER_OFF, TaskType.RESTART, TaskType.LOCK})


class TaskStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    NEEDS_APPROVAL = "needs_approval"
    COMPLETED = "completed"
    FAILED = "failed"
    DENIED = "denied"


class Task(BaseModel):
    task_id: str = Field(default_factory=new_uuid)
    type: str = "run_instruction"
    instruction: str
    require_approval: bool = False
    created_at: datetime = Field(default_factory=utc_now)


class TaskResult(BaseModel):
    # task_id is filled in by the TaskRunner; backends may leave it empty.
    task_id: str = ""
    status: TaskStatus
    summary: str = ""
    logs: list[str] = Field(default_factory=list)
    artifacts: list[dict[str, Any]] = Field(default_factory=list)


# --- observation models -------------------------------------------------------


class Observation(BaseModel):
    description: str = ""
    screenshot_b64: str | None = None  # PNG, base64-encoded
    captured_at: datetime = Field(default_factory=utc_now)


class AccessibilityTree(BaseModel):
    root: dict[str, Any] = Field(default_factory=dict)
    captured_at: datetime = Field(default_factory=utc_now)
