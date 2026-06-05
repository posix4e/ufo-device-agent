"""DeviceAgentUserWorker — user-session automation worker (STUB).

This is the process that must run INSIDE the logged-in user's Windows session,
because it is the one that will eventually:
  * call UFO² (HostAgent / AppAgent),
  * capture screenshots,
  * walk the UI Automation (UIA) tree,
  * send keyboard/mouse input.

None of that works from session 0 (services) — hence the split from
service_stub.DeviceAgentService.

Intended production IPC: the service exposes tasks to the worker over a named
pipe or a localhost-only WebSocket; the worker streams logs/results back. The
worker holds NO device credentials — only the service talks to the network.

MVP: the agent runs as a single process in the user's session, so the
"worker" is just the automation backend hosted in-process. This class exists
to mark the seam where the split will happen.
"""

from __future__ import annotations

from ..automation.base import DeviceAutomationBackend


class DeviceAgentUserWorker:
    """Hosts an automation backend inside the user's session.

    MVP: trivial in-process wrapper. Production: separate process started by
    DeviceAgentService via CreateProcessAsUser, speaking IPC.
    """

    def __init__(self, backend: DeviceAutomationBackend) -> None:
        self.backend = backend

    async def serve_ipc(self) -> None:
        # TODO(production): listen on a named pipe / localhost WS, accept task
        # requests from DeviceAgentService, run them via self.backend, stream
        # logs back. Authenticate the pipe (e.g., per-boot random token passed
        # at process creation).
        raise NotImplementedError("MVP hosts the backend in-process; no IPC yet")
