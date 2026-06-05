"""MCP bridge: expose control-plane device operations as MCP tools.

This package talks to the CONTROL PLANE admin API, not to devices directly —
the control plane remains the single chokepoint for device access.
"""

from .tools import McpBridgeClient

__all__ = ["McpBridgeClient"]
