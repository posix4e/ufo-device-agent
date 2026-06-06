"""Basic Windows-native backend: REAL (but primitive) GUI actions, no UFO².

A stepping stone toward UFO²: it actually opens apps, types text (WScript
SendKeys) and captures real screenshots — enough to demo "submit a task
remotely, watch Notepad open on the PC". It does NOT plan or verify
anything; ``run_instruction`` is a dumb regex over the instruction
("open X ... type Y"). Real planning/grounding is UFO²'s job (ufo_backend).

CAVEATS
 - Windows only, and the agent must run in the interactive desktop session
   (your logged-in / RDP session), or input lands on an invisible desktop.
 - SendKeys types into whatever has focus. Policy still gates at task level,
   but treat this backend as demo-grade.
"""

from __future__ import annotations

import asyncio
import base64
import re
import subprocess
import sys
import tempfile
from pathlib import Path

from ..models import AccessibilityTree, Observation, TaskResult, TaskStatus
from .base import DeviceAutomationBackend

CREATE_NO_WINDOW = 0x08000000  # don't flash extra consoles for helper commands

# friendly name -> launch command (anything else is passed to `start` as-is)
APP_ALIASES = {
    "notepad": "notepad",
    "calculator": "calc",
    "calc": "calc",
    "paint": "mspaint",
    "explorer": "explorer",
    "edge": "msedge",
    "chrome": "chrome",
    "wordpad": "wordpad",
}

_SENDKEYS_SPECIAL = set("+^%~(){}[]")

_SCREENSHOT_PS = r"""
Add-Type -AssemblyName System.Windows.Forms,System.Drawing
$b = [System.Windows.Forms.SystemInformation]::VirtualScreen
$bmp = New-Object System.Drawing.Bitmap $b.Width, $b.Height
$g = [System.Drawing.Graphics]::FromImage($bmp)
$g.CopyFromScreen($b.X, $b.Y, 0, 0, $bmp.Size)
$bmp.Save('{path}', [System.Drawing.Imaging.ImageFormat]::Png)
"""


def _sendkeys_escape(text: str) -> str:
    out = []
    for ch in text:
        if ch in _SENDKEYS_SPECIAL:
            out.append("{" + ch + "}")
        elif ch == "\n":
            out.append("{ENTER}")
        elif ch == "\t":
            out.append("{TAB}")
        else:
            out.append(ch)
    return "".join(out)


def _run_hidden(args: list[str], timeout: float = 30) -> subprocess.CompletedProcess:
    return subprocess.run(
        args, capture_output=True, text=True, timeout=timeout, creationflags=CREATE_NO_WINDOW
    )


class BasicAutomationBackend(DeviceAutomationBackend):
    name = "basic"

    def __init__(self) -> None:
        super().__init__()
        if sys.platform != "win32":
            raise RuntimeError("the 'basic' backend only works on Windows — this is a Windows device agent")

    # --- observation -----------------------------------------------------------

    async def observe_screen(self) -> Observation:
        path = Path(tempfile.gettempdir()) / "ufo_agent_shot.png"
        script = _SCREENSHOT_PS.format(path=str(path).replace("'", "''"))
        result = await asyncio.to_thread(_run_hidden, ["powershell", "-NoProfile", "-Command", script])
        if result.returncode != 0 or not path.exists():
            return Observation(description=f"screenshot failed: {result.stderr.strip()[:200]}")
        data = base64.b64encode(path.read_bytes()).decode()
        return Observation(description="full virtual-screen capture", screenshot_b64=data)

    async def observe_accessibility_tree(self) -> AccessibilityTree:
        # Real UIA walking is UFO² territory; report window titles only.
        ps = (
            "Get-Process | Where-Object {$_.MainWindowTitle} | "
            "Select-Object -ExpandProperty MainWindowTitle"
        )
        result = await asyncio.to_thread(_run_hidden, ["powershell", "-NoProfile", "-Command", ps])
        windows = [t for t in result.stdout.splitlines() if t.strip()]
        return AccessibilityTree(
            root={"role": "desktop", "children": [{"role": "window", "name": w} for w in windows]}
        )

    # --- primitive actions --------------------------------------------------------

    async def open_app(self, app_name: str) -> TaskResult:
        cmd = APP_ALIASES.get(app_name.strip().lower(), app_name.strip())
        await self.emit_log(f"(basic) launching: {cmd}")
        await asyncio.to_thread(_run_hidden, ["cmd", "/c", "start", "", cmd])
        await asyncio.sleep(1.5)  # give the window time to appear and take focus
        return TaskResult(status=TaskStatus.COMPLETED, summary=f"launched {cmd}")

    async def type_text(self, text: str) -> TaskResult:
        await self.emit_log(f"(basic) typing {len(text)} characters into the focused window")
        escaped = _sendkeys_escape(text).replace("'", "''")
        ps = f"$ws = New-Object -ComObject WScript.Shell; Start-Sleep -m 300; $ws.SendKeys('{escaped}')"
        result = await asyncio.to_thread(_run_hidden, ["powershell", "-NoProfile", "-Command", ps])
        if result.returncode != 0:
            return TaskResult(status=TaskStatus.FAILED, summary=f"SendKeys failed: {result.stderr.strip()[:200]}")
        return TaskResult(status=TaskStatus.COMPLETED, summary=f"typed {len(text)} characters")

    async def press_keys(self, keys: list[str]) -> TaskResult:
        mapping = {"enter": "{ENTER}", "tab": "{TAB}", "esc": "{ESC}", "ctrl": "^", "alt": "%", "shift": "+", "win": "^{ESC}"}
        seq = "".join(mapping.get(k.lower(), k) for k in keys)
        return await self.type_text(seq)  # SendKeys handles chords like ^s

    async def click(self, target: str) -> TaskResult:
        # No grounding without UFO²: we cannot find `target` on screen.
        return TaskResult(
            status=TaskStatus.FAILED,
            summary="(basic) click-by-description needs UFO² grounding; use --backend ufo",
        )

    # --- "planning" ------------------------------------------------------------------

    async def run_instruction(self, instruction: str) -> TaskResult:
        """Regex-level understanding: 'open <app>' and/or 'type <text>'."""
        logs: list[str] = []
        did_anything = False

        m_open = re.search(
            r"\bopen (?:the )?([A-Za-z0-9 ._-]+?)(?=\s+(?:and|then)\b|[,.]|$)", instruction, re.I
        )
        m_type = re.search(r"\btypes?\s+(?:in\s+)?['\"]?(.+?)['\"]?\s*\.?$", instruction, re.I)

        if m_open:
            result = await self.open_app(m_open.group(1))
            logs.extend(result.logs or [result.summary])
            if result.status != TaskStatus.COMPLETED:
                return TaskResult(status=TaskStatus.FAILED, summary=result.summary, logs=logs)
            did_anything = True

        if m_type:
            result = await self.type_text(m_type.group(1))
            logs.extend(result.logs or [result.summary])
            if result.status != TaskStatus.COMPLETED:
                return TaskResult(status=TaskStatus.FAILED, summary=result.summary, logs=logs)
            did_anything = True

        if not did_anything:
            return TaskResult(
                status=TaskStatus.FAILED,
                summary=(
                    "(basic) could not parse instruction — this backend only understands "
                    "'open <app>' and 'type <text>'. Full natural-language tasks need UFO² "
                    "(--backend ufo)."
                ),
            )

        return TaskResult(
            status=TaskStatus.COMPLETED,
            summary=f"(basic) executed: {instruction}",
            logs=logs,
        )
