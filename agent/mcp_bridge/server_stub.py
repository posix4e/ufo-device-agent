"""MCP server exposing the device fleet to AI agents.

Requires the optional dependency:  pip install -e ".[mcp]"
Run (stdio transport):             python -m agent.mcp_bridge.server_stub

Claude Desktop / Claude Code config example:
    {
      "mcpServers": {
        "ufo-device-agent": {
          "command": "python",
          "args": ["-m", "agent.mcp_bridge.server_stub"],
          "env": {
            "UFO_CP_URL": "http://localhost:8000",
            "UFO_CP_ADMIN_TOKEN": "dev-admin-token"
          }
        }
      }
    }
"""

from __future__ import annotations

import os
from typing import Any

from .tools import McpBridgeClient

# mcp is an optional extra: pip install -e ".[mcp]". If it's missing, this
# import fails loudly right here — no degraded mode.
from mcp.server.fastmcp import FastMCP


def build_server() -> FastMCP:
    client = McpBridgeClient(
        base_url=os.environ.get("UFO_CP_URL", "http://localhost:8000"),
        admin_token=os.environ.get("UFO_CP_ADMIN_TOKEN", "dev-admin-token"),
    )
    mcp = FastMCP("ufo-device-agent")

    @mcp.tool()
    async def list_devices() -> list[dict[str, Any]]:
        """List paired Windows devices and whether each is online."""
        return await client.list_devices()

    @mcp.tool()
    async def get_device_status(device_id: str) -> dict[str, Any]:
        """Get a device's latest status (backend, paused, current task, last result)."""
        return await client.get_device_status(device_id)

    @mcp.tool()
    async def run_device_task(device_id: str, instruction: str, require_approval: bool = False) -> dict[str, Any]:
        """Run a natural-language GUI task on a device (e.g. 'Open Notepad and type hello').

        Risky tasks may pause for human approval on the device per its policy."""
        return await client.run_device_task(device_id, instruction, require_approval)

    @mcp.tool()
    async def observe_screen(device_id: str) -> dict[str, Any]:
        """Request a screenshot from the device and return the latest stored capture."""
        return await client.observe_screen(device_id)

    @mcp.tool()
    async def approve_action(device_id: str, task_id: str) -> dict[str, Any]:
        """Approve a task that is waiting for approval on the device."""
        return await client.approve_action(device_id, task_id)

    @mcp.tool()
    async def deny_action(device_id: str, task_id: str) -> dict[str, Any]:
        """Deny a task that is waiting for approval on the device."""
        return await client.deny_action(device_id, task_id)

    @mcp.tool()
    async def pause_device(device_id: str) -> dict[str, Any]:
        """Pause task execution on a device."""
        return await client.pause_device(device_id)

    @mcp.tool()
    async def resume_device(device_id: str) -> dict[str, Any]:
        """Resume task execution on a paused device."""
        return await client.resume_device(device_id)

    @mcp.tool()
    async def get_device_events(device_id: str, limit: int = 50) -> list[dict[str, Any]]:
        """Recent events for a device: task logs, completions, approval requests."""
        return await client.get_device_events(device_id, limit)

    return mcp


def main() -> None:
    build_server().run()  # stdio transport


if __name__ == "__main__":
    main()
