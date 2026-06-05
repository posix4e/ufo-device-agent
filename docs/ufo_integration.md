# Integrating Microsoft UFO²

UFO² (https://github.com/microsoft/UFO) is the GUI automation engine — the
"Desktop AgentOS" that plans and executes multi-step UI work via a HostAgent
(picks/launches the app) and AppAgents (drive each app through UIA + vision).
This project is the *end-user wrapper* around it: pairing, connectivity,
policy, approvals, and packaging. The integration seam is exactly one class:
`agent/automation/ufo_backend.py::UfoAutomationBackend`.

## Step-by-step

1. **Windows machine** with Python 3.11+ (UFO² requires >= 3.10).

2. **Install UFO² into the agent's venv** (it is not on PyPI as of this
   writing — clone and install its requirements):

   ```powershell
   git clone https://github.com/microsoft/UFO.git ..\UFO
   .venv\Scripts\pip install -r ..\UFO\requirements.txt
   # make `import ufo` resolvable, e.g.:
   .venv\Scripts\pip install -e ..\UFO    # if/when UFO ships a setup/pyproject
   # or add the UFO checkout to sys.path in ufo_backend.py as a stopgap
   ```

3. **Configure UFO's LLM credentials** — UFO reads its own
   `ufo/config/config.yaml` (OpenAI / Azure OpenAI / etc. for HOST_AGENT and
   APP_AGENT). TODO for the wrapper: generate this file from agent settings
   so end users configure keys once, in our UI, not in UFO's YAML.

4. **Wire `run_instruction`** — the core of the integration:
   - Create a UFO session with the instruction as the request (UFO's
     `SessionFactory` / client session machinery; in CLI form this is what
     `python -m ufo --task <name> -r "<request>"` does).
   - UFO's session loop is synchronous → run it in a thread
     (`asyncio.to_thread`) and forward round/step logs back to the event loop
     via `asyncio.run_coroutine_threadsafe(self.emit_log(...), loop)`.
   - Map the final session state → `TaskStatus`:
     FINISH → COMPLETED, ERROR → FAILED, user-confirmation states →
     NEEDS_APPROVAL (bridge to our approval flow, next point).

5. **Bridge UFO's safety confirmations** — UFO can ask for confirmation
   before sensitive actions. Intercept that prompt and route it through
   `TaskRunner._wait_for_approval` instead of UFO's console input, so the
   approval shows up in the local UI and the operator's view. This gives
   *action-level* policy enforcement (much better than our MVP keyword
   matching at task intake).

6. **Wire observation**:
   - `observe_screen`: UFO's screenshot capture ("photographer") utilities →
     base64 PNG in an `Observation`.
   - `observe_accessibility_tree`: UFO's UIA control inspection (the control
     annotations it builds for grounding) → JSON tree.

7. **Run it**:

   ```powershell
   powershell scripts\dev_start_agent.ps1 -Backend ufo
   # or: python -m agent.main start --backend ufo
   ```

   Nothing else changes: pairing, relay protocol, policy, approvals, and both
   UIs are backend-agnostic.

## Rules for the integration

- `ufo_backend.py` stays the **only** module importing UFO².
- The backend never touches the network — TaskRunner owns events/approvals.
- The agent must run in the logged-in user's session (see
  docs/windows_service_model.md) or UIA/screenshots will fail.
- UFO is chatty: throttle/batch `emit_log` if step logs flood the relay.

## Suggested first test

Pair the device, then submit through the admin UI:

> Open Notepad and type hello from the agent.

Watch `task_log` events stream UFO's plan/act steps, then try a risky one
("Install ...") to see the approval flow gate a real UFO session.
