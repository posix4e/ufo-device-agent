"""Device WebSocket relay.

Devices dial OUT to ``/ws/device?token=<device_token>`` — the control plane
never connects to devices. One socket per device; inbound device events are
recorded in the registry, and operator commands are pushed down the same
socket via ConnectionManager.send().
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Query, WebSocket, WebSocketDisconnect

from .device_registry import DeviceRegistry


class ConnectionManager:
    def __init__(self) -> None:
        self._sockets: dict[str, WebSocket] = {}

    def attach(self, device_id: str, ws: WebSocket) -> None:
        self._sockets[device_id] = ws

    def detach(self, device_id: str, ws: WebSocket) -> None:
        if self._sockets.get(device_id) is ws:
            self._sockets.pop(device_id, None)

    def is_connected(self, device_id: str) -> bool:
        return device_id in self._sockets

    async def send(self, device_id: str, type_: str, payload: dict[str, Any]) -> bool:
        """Push a message to a device. Returns False if the device is offline."""
        ws = self._sockets.get(device_id)
        if ws is None:
            return False
        try:
            await ws.send_json({"type": type_, "payload": payload})
        except Exception:
            self._sockets.pop(device_id, None)
            return False
        return True


router = APIRouter()


@router.websocket("/ws/device")
async def device_ws(websocket: WebSocket, token: str = Query(...)) -> None:
    registry: DeviceRegistry = websocket.app.state.registry
    manager: ConnectionManager = websocket.app.state.connections

    device = registry.by_token(token)
    if device is None:
        # 4401: our convention for "invalid device token".
        await websocket.close(code=4401, reason="invalid device token")
        return

    await websocket.accept()
    manager.attach(device.device_id, websocket)
    registry.touch(device.device_id)
    registry.add_event(device.device_id, "relay_connected", {})
    try:
        while True:
            data = await websocket.receive_json()
            _handle_device_message(registry, device.device_id, data)
    except WebSocketDisconnect:
        pass
    except Exception:
        pass  # malformed frame or transport error — drop the connection
    finally:
        manager.detach(device.device_id, websocket)
        registry.add_event(device.device_id, "relay_disconnected", {})


def _handle_device_message(registry: DeviceRegistry, device_id: str, data: Any) -> None:
    if not isinstance(data, dict):
        return
    mtype = str(data.get("type", "unknown"))
    payload = data.get("payload") or {}
    registry.touch(device_id)

    if mtype == "device_status":
        # Heartbeats update latest status but don't spam the event log.
        registry.set_last_status(device_id, payload)
        return

    if mtype == "screenshot_available" and payload.get("screenshot_b64"):
        registry.set_screenshot(device_id, payload)
        # Keep the event log lightweight — strip the image bytes.
        payload = {k: v for k, v in payload.items() if k != "screenshot_b64"} | {"screenshot": "stored"}

    registry.add_event(device_id, mtype, payload)
