"""Agent settings. Everything is env-overridable with the ``UFO_AGENT_`` prefix.

Examples:
    UFO_AGENT_BACKEND=ufo
    UFO_AGENT_LOCAL_UI_PORT=9000
    UFO_AGENT_DATA_DIR=C:\\temp\\agent-data
"""

from __future__ import annotations

import platform
from pathlib import Path
from typing import Literal

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

AGENT_VERSION = "0.1.0"


class AgentSettings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="UFO_AGENT_", env_file=".env", extra="ignore")

    # Override the data directory (defaults to %LOCALAPPDATA%\UfoDeviceAgent on Windows).
    data_dir: Path | None = None

    # The local UI must stay loopback-only: it has no auth and can approve actions.
    local_ui_host: str = "127.0.0.1"
    local_ui_port: int = 8766

    # basic: real native Windows actions (default) | ufo: UFO² (milestone 2)
    backend: Literal["basic", "ufo"] = "basic"

    device_name: str = Field(default_factory=platform.node)

    heartbeat_seconds: float = 20.0
    reconnect_min_seconds: float = 1.0
    reconnect_max_seconds: float = 30.0
    approval_timeout_seconds: float = 600.0
