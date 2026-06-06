"""Admin / operator HTTP API.

WARNING — NOT PRODUCTION AUTH. A single shared token (X-Admin-Token header,
default "dev-admin-token", override with UFO_CP_ADMIN_TOKEN) guards every
endpoint. Replace with real multi-tenant authn/z + audit logging before
exposing this beyond localhost.
"""

from __future__ import annotations

import os
from typing import Any

from fastapi import APIRouter, Depends, Header, HTTPException, Request

from .models import ApprovalAction, TaskSubmission, new_uuid, utc_now

DEV_ADMIN_TOKEN = os.environ.get("UFO_CP_ADMIN_TOKEN", "dev-admin-token")


async def require_admin(x_admin_token: str = Header(default="")) -> None:
    if x_admin_token != DEV_ADMIN_TOKEN:
        raise HTTPException(status_code=401, detail="invalid admin token (send X-Admin-Token header)")


router = APIRouter(prefix="/api/admin", dependencies=[Depends(require_admin)])


# --- pairing ----------------------------------------------------------------------


@router.post("/pairing")
async def create_pairing_code(request: Request) -> dict[str, Any]:
    info = request.app.state.pairing.create_code()
    return {
        "code": info.code,
        "expires_at": info.expires_at.isoformat(),
        "qr_png_url": f"/api/pairing/{info.code}/qr.png",
    }


# --- devices -----------------------------------------------------------------------


@router.get("/devices")
async def list_devices(request: Request) -> list[dict[str, Any]]:
    registry = request.app.state.registry
    connections = request.app.state.connections
    out = []
    for device in registry.list_devices():
        item = device.public()
        item["online"] = connections.is_connected(device.device_id)
        item["last_status"] = registry.last_status(device.device_id)
        out.append(item)
    return out


@router.delete("/devices/{device_id}")
async def delete_device(device_id: str, request: Request) -> dict[str, Any]:
    """Forget a device: drop any live socket, then erase its record + history.

    The device will need to be re-paired (its stored token is now unknown)."""
    registry = request.app.state.registry
    if registry.get(device_id) is None:
        raise HTTPException(status_code=404, detail="unknown device")
    await request.app.state.connections.close(device_id, reason="device deleted")
    registry.remove(device_id)
    return {"ok": True, "device_id": device_id}


@router.get("/devices/{device_id}/events")
async def device_events(device_id: str, request: Request, limit: int = 100) -> list[dict[str, Any]]:
    registry = request.app.state.registry
    if registry.get(device_id) is None:
        raise HTTPException(status_code=404, detail="unknown device")
    return [e.model_dump(mode="json") for e in registry.events(device_id, limit)]


@router.get("/devices/{device_id}/screenshot")
async def device_screenshot(device_id: str, request: Request) -> dict[str, Any]:
    shot = request.app.state.registry.get_screenshot(device_id)
    if shot is None:
        raise HTTPException(status_code=404, detail="no screenshot stored — POST .../observe first")
    return shot


# --- commands ------------------------------------------------------------------------


async def _send_or_409(request: Request, device_id: str, type_: str, payload: dict[str, Any]) -> None:
    registry = request.app.state.registry
    if registry.get(device_id) is None:
        raise HTTPException(status_code=404, detail="unknown device")
    delivered = await request.app.state.connections.send(device_id, type_, payload)
    if not delivered:
        raise HTTPException(status_code=409, detail="device is offline")
    registry.add_event(device_id, f"sent:{type_}", payload)


@router.post("/devices/{device_id}/tasks")
async def submit_task(device_id: str, submission: TaskSubmission, request: Request) -> dict[str, Any]:
    task = {
        "task_id": new_uuid(),
        "type": submission.type,
        "instruction": submission.instruction,
        "require_approval": submission.require_approval,
        "created_at": utc_now().isoformat(),
    }
    await _send_or_409(request, device_id, "run_task", task)
    return {"ok": True, "task_id": task["task_id"]}


@router.post("/devices/{device_id}/observe")
async def observe_screen(device_id: str, request: Request) -> dict[str, Any]:
    await _send_or_409(request, device_id, "observe_screen", {})
    return {"ok": True, "note": "screenshot arrives asynchronously; GET .../screenshot shortly"}


@router.post("/devices/{device_id}/approve")
async def approve_action(device_id: str, action: ApprovalAction, request: Request) -> dict[str, Any]:
    await _send_or_409(request, device_id, "approve_action", {"task_id": action.task_id})
    return {"ok": True}


@router.post("/devices/{device_id}/deny")
async def deny_action(device_id: str, action: ApprovalAction, request: Request) -> dict[str, Any]:
    await _send_or_409(request, device_id, "deny_action", {"task_id": action.task_id})
    return {"ok": True}


@router.post("/devices/{device_id}/pause")
async def pause_device(device_id: str, request: Request) -> dict[str, Any]:
    await _send_or_409(request, device_id, "pause", {})
    return {"ok": True}


@router.post("/devices/{device_id}/resume")
async def resume_device(device_id: str, request: Request) -> dict[str, Any]:
    await _send_or_409(request, device_id, "resume", {})
    return {"ok": True}


@router.post("/devices/{device_id}/update")
async def update_device(device_id: str, request: Request) -> dict[str, Any]:
    """Ask the device to self-update to the latest published release.

    Only the packaged exe acts on this; a source-run agent reports update_failed.
    The device goes offline -> online at the new version if it updates."""
    await _send_or_409(request, device_id, "update_agent", {})
    return {"ok": True, "note": "update requested; watch the device's version in the status"}
