"""DeviceAgentService — background supervisor (STUB).

Intended production shape
-------------------------
A Windows service that:
  * starts at boot (no user login required for connectivity),
  * owns the outbound relay WebSocket connection and device credentials,
  * supervises/launches the user-session worker (user_worker.py) when a user
    logs in, and proxies tasks to it over local IPC (named pipe or
    localhost-only WebSocket),
  * restarts the worker if it crashes.

Why a separate service at all? Windows services run in session 0 and CANNOT
access the interactive desktop — no screenshots, no UI Automation, no input.
So the service handles connectivity/identity, and the worker (running in the
logged-in user's session) does the actual GUI automation.

Production packaging options (pick one later):
  * pywin32 ``win32serviceutil.ServiceFramework`` — classic Python service.
  * WinSW or NSSM — wrap the plain Python/exe process as a service with a
    small XML/CLI config; easiest path for an MVP installer.
  * MSIX with a startup task / Windows service extension.

For the MVP, none of this runs: ``python -m agent.main start`` runs everything
(relay client + task runner + local UI + in-process backend) in a single
foreground process inside the user's session, which is exactly what GUI
automation needs anyway.
"""

from __future__ import annotations


class DeviceAgentService:
    """Placeholder for the production background supervisor."""

    def start(self) -> None:
        # TODO: pywin32 service main: connect relay, spawn user worker via
        # CreateProcessAsUser in the active console session, supervise it.
        raise NotImplementedError("MVP runs in-process; see module docstring and docs/windows_service_model.md")

    def stop(self) -> None:
        raise NotImplementedError
