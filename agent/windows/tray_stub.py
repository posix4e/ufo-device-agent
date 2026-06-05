"""DeviceAgentTray — system tray app (STUB).

Safety requirement: when the agent is running, the user must always be able
to SEE that it is running and reach the controls. In MVP that is the local web
UI (http://127.0.0.1:8766). Production should add a tray icon that:

  * shows online/paired/paused state at a glance (icon color/badge),
  * shows a notification when a task starts and when approval is required,
  * offers menu items: Open dashboard, Pause/Resume, Quit,
  * never hides itself — no stealth mode, ever.

Implementation candidates:
  * pystray + Pillow — simple, pure Python, fine for MVP+1.
  * Windows App SDK / winrt notifications for proper toasts.
  * If we package as MSIX later, the tray app is its own small exe.
"""

from __future__ import annotations


class DeviceAgentTray:
    """Placeholder for the production tray app."""

    def run(self) -> None:
        # TODO: pystray icon wired to the local UI's /api/status endpoint;
        # menu: Open dashboard / Pause / Resume / Quit.
        raise NotImplementedError("MVP uses the local web UI; see module docstring")
