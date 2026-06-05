"""Local persistent storage for the agent.

Targets Windows first (``%LOCALAPPDATA%\\UfoDeviceAgent``) but works
cross-platform so the agent can be developed on macOS/Linux.

Files:
    state.json   - device identity / pairing state (contains the device token!)
    policy.yaml  - local safety policy (see agent/policy.py)
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

from pydantic import BaseModel

APP_DIR_NAME = "UfoDeviceAgent"


def default_data_dir() -> Path:
    if sys.platform == "win32":
        base = Path(os.environ.get("LOCALAPPDATA", str(Path.home() / "AppData" / "Local")))
        return base / APP_DIR_NAME
    if sys.platform == "darwin":
        return Path.home() / "Library" / "Application Support" / APP_DIR_NAME
    base = Path(os.environ.get("XDG_DATA_HOME", str(Path.home() / ".local" / "share")))
    return base / "ufo-device-agent"


class AgentState(BaseModel):
    """Pairing / identity state persisted between runs."""

    install_id: str | None = None  # generated locally on first run
    device_secret: str | None = None  # local random secret (future: real keypair)
    device_id: str | None = None  # assigned by the control plane on claim
    device_name: str | None = None
    relay_url: str | None = None  # http(s) base URL of the control plane
    relay_ws_url: str | None = None  # ws(s) URL of the device WebSocket endpoint
    device_token: str | None = None  # bearer token issued when the pairing code is claimed

    @property
    def paired(self) -> bool:
        return bool(self.device_token and self.relay_ws_url)


class AgentStorage:
    def __init__(self, data_dir: Path | None = None) -> None:
        self.data_dir = data_dir or default_data_dir()
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self.state_path = self.data_dir / "state.json"
        self.policy_path = self.data_dir / "policy.yaml"

    def load_state(self) -> AgentState:
        if self.state_path.exists():
            return AgentState.model_validate_json(self.state_path.read_text(encoding="utf-8"))
        return AgentState()

    def save_state(self, state: AgentState) -> None:
        # NOTE: contains the device token in plaintext. LOCALAPPDATA is per-user,
        # which is acceptable for an MVP. Production should protect the token with
        # DPAPI (CryptProtectData) or the Windows Credential Manager.
        self.state_path.write_text(state.model_dump_json(indent=2), encoding="utf-8")

    def ensure_policy_file(self, default_yaml: str) -> Path:
        if not self.policy_path.exists():
            self.policy_path.write_text(default_yaml, encoding="utf-8")
        return self.policy_path
