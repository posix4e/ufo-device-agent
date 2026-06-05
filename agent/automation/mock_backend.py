"""Mock automation backend.

Simulates GUI work so the full vertical slice (pairing -> relay -> task ->
streamed logs -> completion) runs on any machine, with no UFO², no Windows,
and no LLM credentials. This is the default backend.
"""

from __future__ import annotations

import asyncio

from ..models import AccessibilityTree, Observation, TaskResult, TaskStatus
from .base import DeviceAutomationBackend

# 1x1 grey PNG, base64 — stand-in for a real screenshot.
PLACEHOLDER_PNG_B64 = (
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJ"
    "AAAADUlEQVR42mP8z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg=="
)


class MockAutomationBackend(DeviceAutomationBackend):
    name = "mock"

    async def observe_screen(self) -> Observation:
        await asyncio.sleep(0.2)
        return Observation(
            description="(mock) Desktop with taskbar; open windows: ['Notepad - Untitled']",
            screenshot_b64=PLACEHOLDER_PNG_B64,
        )

    async def observe_accessibility_tree(self) -> AccessibilityTree:
        await asyncio.sleep(0.2)
        return AccessibilityTree(
            root={
                "role": "desktop",
                "name": "(mock desktop)",
                "children": [{"role": "window", "name": "Notepad - Untitled", "children": []}],
            }
        )

    async def run_instruction(self, instruction: str) -> TaskResult:
        steps = [
            f"(mock) Parsing instruction: {instruction!r}",
            "(mock) Capturing screen state",
            "(mock) Planning UI actions (this is where UFO² HostAgent/AppAgent would run)",
            "(mock) Executing step 1/3: locate target window",
            "(mock) Executing step 2/3: perform UI actions",
            "(mock) Executing step 3/3: verify result",
        ]
        logs: list[str] = []
        for step in steps:
            await asyncio.sleep(0.6)  # make progress visible in the UIs
            logs.append(step)
            await self.emit_log(step)
        return TaskResult(
            status=TaskStatus.COMPLETED,
            summary=f"(mock) Simulated execution of: {instruction}",
            logs=logs,
        )

    async def open_app(self, app_name: str) -> TaskResult:
        await self.emit_log(f"(mock) Opening app: {app_name}")
        await asyncio.sleep(0.4)
        return TaskResult(status=TaskStatus.COMPLETED, summary=f"(mock) Opened {app_name}")

    async def click(self, target: str) -> TaskResult:
        await self.emit_log(f"(mock) Clicking: {target}")
        await asyncio.sleep(0.2)
        return TaskResult(status=TaskStatus.COMPLETED, summary=f"(mock) Clicked {target}")

    async def type_text(self, text: str) -> TaskResult:
        await self.emit_log(f"(mock) Typing {len(text)} characters")
        await asyncio.sleep(0.2)
        return TaskResult(status=TaskStatus.COMPLETED, summary=f"(mock) Typed text ({len(text)} chars)")

    async def press_keys(self, keys: list[str]) -> TaskResult:
        await self.emit_log(f"(mock) Pressing keys: {'+'.join(keys)}")
        await asyncio.sleep(0.2)
        return TaskResult(status=TaskStatus.COMPLETED, summary=f"(mock) Pressed {'+'.join(keys)}")
