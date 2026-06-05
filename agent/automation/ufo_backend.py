"""UFO² automation backend (stub).

This is the ONLY module that may import or talk to Microsoft UFO²
(https://github.com/microsoft/UFO). Keep all UFO-specific glue here so the
rest of the agent stays engine-agnostic.

Integration plan (details in docs/ufo_integration.md):

 1. On a Windows machine, install UFO² into the same venv as this agent
    (clone the repo, ``pip install -r requirements.txt`` per UFO docs, or
    vendor it as a dependency once it is pip-installable).
 2. Configure UFO's LLM credentials out of band (UFO reads its own
    ``ufo/config/config.yaml``). The wrapper should eventually template this
    file from agent settings so end users never edit it by hand.
 3. ``run_instruction``: create a UFO session for the request and pump its
    rounds. UFO's HostAgent picks the app, AppAgent executes steps; forward
    each round/step log through ``self.emit_log(...)`` so the operator and
    local UI see live progress.
 4. ``observe_screen``: use UFO's screenshot utilities (the "photographer"
    capture module) and return a base64 PNG.
 5. ``observe_accessibility_tree``: surface UFO's UIA control inspection
    (the control annotations it builds for grounding) as a JSON tree.
 6. Map UFO's final session state to TaskStatus (FINISH -> COMPLETED,
    ERROR -> FAILED, CONFIRM/pending -> NEEDS_APPROVAL — UFO's own
    sensitive-action confirmation should be bridged to our approval flow).

IMPORTANT: this process must run in the logged-in user's Windows session
(see agent/windows/user_worker.py) or screenshots and UIA will not work.
"""

from __future__ import annotations

from ..models import AccessibilityTree, Observation, TaskResult
from .base import DeviceAutomationBackend


class BackendUnavailableError(RuntimeError):
    pass


def ufo_available() -> bool:
    """True if the UFO² package is importable in this environment."""
    try:
        import ufo  # noqa: F401  # type: ignore[import-not-found]
    except ImportError:
        return False
    return True


_NOT_WIRED = (
    "UfoAutomationBackend is not wired up yet. "
    "Run with the default mock backend (--backend mock), or see "
    "docs/ufo_integration.md for the integration plan."
)


class UfoAutomationBackend(DeviceAutomationBackend):
    name = "ufo"

    def __init__(self) -> None:
        super().__init__()
        if not ufo_available():
            raise BackendUnavailableError(
                "UFO² is not installed in this environment. "
                "Install Microsoft UFO² on Windows first (see docs/ufo_integration.md)."
            )
        # TODO: initialize UFO configuration here (LLM keys, model selection),
        # ideally generated from agent settings rather than hand-edited YAML.

    async def observe_screen(self) -> Observation:
        # TODO: capture the desktop via UFO's screenshot utilities; return
        # Observation(description=..., screenshot_b64=<base64 PNG>).
        raise NotImplementedError(_NOT_WIRED)

    async def observe_accessibility_tree(self) -> AccessibilityTree:
        # TODO: walk the UIA tree via UFO's control inspection and serialize it.
        raise NotImplementedError(_NOT_WIRED)

    async def run_instruction(self, instruction: str) -> TaskResult:
        # TODO: the core integration —
        #   session = <create UFO session with `instruction` as the request>
        #   for each round/step: await self.emit_log(<step description>)
        #   return TaskResult(status=<mapped from session state>, summary=...)
        # UFO's blocking session loop should run in a thread
        # (asyncio.to_thread) with log forwarding back to the event loop.
        raise NotImplementedError(_NOT_WIRED)

    async def open_app(self, app_name: str) -> TaskResult:
        # TODO: delegate to UFO's HostAgent app selection / launch.
        raise NotImplementedError(_NOT_WIRED)

    async def click(self, target: str) -> TaskResult:
        # TODO: ground `target` against UIA controls, then click via UFO executor.
        raise NotImplementedError(_NOT_WIRED)

    async def type_text(self, text: str) -> TaskResult:
        # TODO: send text to the focused control via UFO executor.
        raise NotImplementedError(_NOT_WIRED)

    async def press_keys(self, keys: list[str]) -> TaskResult:
        # TODO: send a key chord via UFO executor.
        raise NotImplementedError(_NOT_WIRED)
