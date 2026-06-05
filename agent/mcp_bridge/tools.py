"""Typed client for the control plane admin API — the backing for MCP tools.

Each method maps 1:1 to an intended MCP tool (see server_stub.py):
    list_devices, get_device_status, run_device_task, observe_screen,
    approve_action, deny_action, pause_device, resume_device
"""

from __future__ import annotations

from typing import Any

import httpx


class McpBridgeClient:
    def __init__(self, base_url: str = "http://localhost:8000", admin_token: str = "dev-admin-token") -> None:
        self.base_url = base_url.rstrip("/")
        self._headers = {"X-Admin-Token": admin_token}

    async def _request(self, method: str, path: str, json: dict[str, Any] | None = None) -> Any:
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.request(method, f"{self.base_url}{path}", json=json, headers=self._headers)
        resp.raise_for_status()
        return resp.json()

    async def list_devices(self) -> list[dict[str, Any]]:
        """List all paired devices and whether each is online."""
        return await self._request("GET", "/api/admin/devices")

    async def get_device_status(self, device_id: str) -> dict[str, Any]:
        """Get a device's latest status snapshot (backend, paused, current task...)."""
        devices = await self.list_devices()
        for d in devices:
            if d["device_id"] == device_id:
                return d
        raise ValueError(f"unknown device: {device_id}")

    async def run_device_task(
        self, device_id: str, instruction: str, require_approval: bool = False
    ) -> dict[str, Any]:
        """Submit a natural-language task to a device. Returns {ok, task_id}."""
        return await self._request(
            "POST",
            f"/api/admin/devices/{device_id}/tasks",
            json={"instruction": instruction, "require_approval": require_approval},
        )

    async def observe_screen(self, device_id: str) -> dict[str, Any]:
        """Ask the device for a screenshot; returns the latest stored one.

        Note: capture is async — the device pushes screenshot_available after
        this returns. Poll get_screenshot or check events for freshness.
        """
        await self._request("POST", f"/api/admin/devices/{device_id}/observe")
        return await self._request("GET", f"/api/admin/devices/{device_id}/screenshot")

    async def approve_action(self, device_id: str, task_id: str) -> dict[str, Any]:
        """Approve a task waiting on approval_required."""
        return await self._request("POST", f"/api/admin/devices/{device_id}/approve", json={"task_id": task_id})

    async def deny_action(self, device_id: str, task_id: str) -> dict[str, Any]:
        """Deny a task waiting on approval_required."""
        return await self._request("POST", f"/api/admin/devices/{device_id}/deny", json={"task_id": task_id})

    async def pause_device(self, device_id: str) -> dict[str, Any]:
        """Pause task execution on a device."""
        return await self._request("POST", f"/api/admin/devices/{device_id}/pause")

    async def resume_device(self, device_id: str) -> dict[str, Any]:
        """Resume task execution on a device."""
        return await self._request("POST", f"/api/admin/devices/{device_id}/resume")

    async def get_device_events(self, device_id: str, limit: int = 50) -> list[dict[str, Any]]:
        """Recent events (task logs, completions, approvals) for a device."""
        return await self._request("GET", f"/api/admin/devices/{device_id}/events?limit={limit}")
