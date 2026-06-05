"""Pydantic models for the control plane."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any

from pydantic import BaseModel, Field


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def new_uuid() -> str:
    return str(uuid.uuid4())


class DeviceRecord(BaseModel):
    device_id: str
    device_name: str
    device_token: str  # SECRET — never expose via API; use .public()
    install_id: str | None = None
    created_at: datetime = Field(default_factory=utc_now)
    last_seen: datetime | None = None

    def public(self) -> dict[str, Any]:
        data = self.model_dump(mode="json")
        data.pop("device_token")
        return data


class Event(BaseModel):
    event_id: str = Field(default_factory=new_uuid)
    device_id: str
    type: str
    payload: dict[str, Any] = Field(default_factory=dict)
    ts: datetime = Field(default_factory=utc_now)


class PairingCodeInfo(BaseModel):
    code: str
    created_at: datetime = Field(default_factory=utc_now)
    expires_at: datetime
    claimed_by: str | None = None  # device_id once claimed


class ClaimRequest(BaseModel):
    code: str
    device_name: str = "unnamed-device"
    install_id: str | None = None


class ClaimResponse(BaseModel):
    device_id: str
    device_token: str
    relay_ws_url: str


class TaskSubmission(BaseModel):
    instruction: str
    type: str = "run_instruction"
    require_approval: bool = False


class ApprovalAction(BaseModel):
    task_id: str
