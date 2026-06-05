"""Automation backend interface.

Anything that can look at the screen and drive the GUI implements this.
The mock backend lets the whole pairing/relay/task pipeline run without UFO²
installed; the real implementation lives in ``ufo_backend.py`` and is the only
module allowed to import UFO².

Backends never talk to the network. The TaskRunner owns policy, approvals and
event emission; backends only do (or simulate) GUI work and stream progress
through ``emit_log``.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Awaitable, Callable

from ..models import AccessibilityTree, Observation, TaskResult

LogCallback = Callable[[str], Awaitable[None]]


class DeviceAutomationBackend(ABC):
    name: str = "base"

    def __init__(self) -> None:
        self._log_cb: LogCallback | None = None

    def set_log_callback(self, cb: LogCallback | None) -> None:
        self._log_cb = cb

    async def emit_log(self, message: str) -> None:
        """Stream a progress line to the TaskRunner (and on to the relay/UI)."""
        if self._log_cb is not None:
            await self._log_cb(message)

    # --- observation ---------------------------------------------------------

    @abstractmethod
    async def observe_screen(self) -> Observation: ...

    @abstractmethod
    async def observe_accessibility_tree(self) -> AccessibilityTree: ...

    # --- execution -----------------------------------------------------------

    @abstractmethod
    async def run_instruction(self, instruction: str) -> TaskResult:
        """Main entry point: execute a natural-language instruction."""

    @abstractmethod
    async def open_app(self, app_name: str) -> TaskResult: ...

    @abstractmethod
    async def click(self, target: str) -> TaskResult: ...

    @abstractmethod
    async def type_text(self, text: str) -> TaskResult: ...

    @abstractmethod
    async def press_keys(self, keys: list[str]) -> TaskResult: ...
