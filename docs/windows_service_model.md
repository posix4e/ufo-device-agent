# Windows service / process model

## MVP (today)

One foreground process started by the user (`python -m agent.main start` or
`scripts/dev_start_agent.ps1`), running in the logged-in user's session:

```
agent.main start
 ├─ RelayClient        outbound WS to the control plane
 ├─ TaskRunner         policy + approvals + execution
 ├─ local web UI       http://127.0.0.1:8766
 └─ AutomationBackend  basic native actions (or UFO², in-process)
```

This is the right *session* for GUI automation already — screenshots, UIA and
input all require the interactive user session.

## Production target (three pieces)

```
DeviceAgentService (Windows service, session 0)
  - starts at boot; owns device credentials + the relay connection
  - launches/supervises the user worker when a user logs on
    (CreateProcessAsUser into the active console session)
  - proxies tasks to the worker over local IPC (named pipe or
    localhost-only WS, authenticated with a per-boot token)

DeviceAgentUserWorker (user session)
  - hosts the automation backend (UFO²); does ALL GUI work
  - holds no network credentials; only talks to the service via IPC

DeviceAgentTray (user session)
  - always-visible icon: online/paused state, approval toasts,
    Open dashboard / Pause / Resume / Quit
```

Why the split: Windows services run in **session 0** and cannot touch the
interactive desktop (no screenshots, no UIA, no SendInput). The service gives
boot-time connectivity and supervision; the worker gives desktop access.

Stubs marking these seams: `agent/windows/service_stub.py`,
`user_worker.py`, `tray_stub.py`.

## Packaging options (third milestone)

| Option | Effort | Notes |
|---|---|---|
| **WinSW / NSSM** wrapping a PyInstaller exe | Low | Quickest credible installer: PyInstaller bundles Python (end users never install Python); WinSW/NSSM registers the service. Recommended first step. |
| **pywin32 ServiceFramework** | Medium | Native Python service, more control, more code. |
| **MSIX** | Higher | Store-grade packaging, services + startup tasks supported; best long-term, worst iteration speed. |

Installer flow target: download → install → tray icon appears → "scan this QR
to pair" → done. No Python, no console windows.

## Caveats to design for

- **Locked screen / no session**: GUI automation cannot run on the lock
  screen. The service should report `no_user_session` status rather than fail
  obscurely. (Auto-login / session-unlock helpers are out of scope — they are
  a security can of worms.)
- **UAC prompts**: elevation dialogs run on a secure desktop the worker cannot
  see or click. Tasks needing elevation must surface as approval + manual
  action by the user.
- **Multiple users / fast user switching**: one worker per active session;
  MVP assumes a single user.
