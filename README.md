# ufo-device-agent

[![ci](https://github.com/posix4e/ufo-device-agent/actions/workflows/ci.yml/badge.svg)](https://github.com/posix4e/ufo-device-agent/actions/workflows/ci.yml)

**Install once. Scan QR. Your AI can now safely use this Windows PC.**

An open-source, end-user **Windows device agent** that wraps
[Microsoft UFO²](https://github.com/microsoft/UFO) (the "Desktop AgentOS" for
Windows GUI automation) so a normal person can:

1. Run an installer (dev script today, real installer later).
2. Pair the machine with a control plane by entering a short code (QR planned).
3. See the machine appear **online** in a web dashboard.
4. Let a remote AI agent send it natural-language tasks
   ("Open Bambu Studio and load this 3MF file").
5. **Approve, deny, pause, and watch** everything the agent does, locally.

> ⚠️ **Experimental MVP.** This hands an AI a keyboard and mouse on your PC —
> the default backend really types and really launches apps. Read the
> [security notes](#security) before pointing it at anything that matters.
> It is not hardened, not multi-tenant, and the installer story is still raw.

## Why wrap UFO²?

UFO² is an excellent GUI automation *engine*: it plans multi-step tasks and
drives real Windows apps through UI Automation + vision. But it is a
researcher-facing Python project — config YAMLs, a console, no pairing, no
remote control, no end-user safety surface.

This project is the missing *product shell*:

| UFO² provides | ufo-device-agent provides |
|---|---|
| Task planning + GUI execution | Device identity & QR/code pairing |
| HostAgent / AppAgent loop | Outbound-only relay (no inbound ports / RDP / VPN) |
| UIA + screenshot grounding | Policy: blocked apps, approval-gated risk categories |
| | Local always-visible UI: pause / resume / approve / deny |
| | Control plane: device fleet, tasks, events, screenshots |
| | MCP bridge so any AI agent can drive devices |
| | (Later) one-click installer; no Python needed |

Raw UFO² is **never** exposed to the network. The device dials *out* over one
WebSocket; the only thing listening locally is a loopback-only dashboard.

## Status (milestone 1 — done)

Full vertical slice working with the **basic** native backend (real app
launches, real typing, real screenshots — no LLM planning yet):
create pairing code → pair → device online → submit task → policy check →
(approval if risky) → simulated execution → logs stream back → both UIs live.

- ✅ Control plane: pairing, device WS relay, admin API + web UI, QR codes
- ✅ Agent: pairing, outbound relay client w/ reconnect, task runner,
  policy (keyword MVP), approvals, local web UI, app-data storage
- ✅ MCP bridge (optional extra): list/run/observe/approve/pause tools
- ✅ Device controls: power off / restart / lock (approval-gated)
- ✅ Silent auto-update of the packaged exe (startup check + operator push)
- 🟡 UFO² backend: clean stub with integration plan ([docs/ufo_integration.md](docs/ufo_integration.md))
- 🟡 Windows service/tray: structured stubs ([docs/windows_service_model.md](docs/windows_service_model.md))
- ⬜ QR *scanning* on the agent (QR generation works; manual entry today)
- ⬜ Installer (.exe/MSIX)

## Quickstart (packaged exe)

Every push to `main` builds a standalone **`ufo-agent.exe`** (PyInstaller —
no Python needed on the device) via GitHub Actions; grab it from the latest
[CI run's artifacts](https://github.com/posix4e/ufo-device-agent/actions) or a
[tagged release](https://github.com/posix4e/ufo-device-agent/releases). Then:

```powershell
ufo-agent.exe pair --code ABCD-1234 --relay https://your-control-plane:8000
ufo-agent.exe start            # local UI on http://127.0.0.1:8766
```

(The exe is unsigned — expect a SmartScreen prompt when downloaded via a
browser. The control plane still runs from source for now.)

## Quickstart (dev)

Requires Python 3.11+ on Windows (the control plane alone also runs on
macOS/Linux).

```powershell
# 0. one-time setup
powershell scripts\install_dev.ps1

# 1. terminal 1 — control plane on http://localhost:8000
powershell scripts\dev_start_server.ps1

# 2. open http://localhost:8000  → click "Create pairing code"  (token: dev-admin-token)

# 3. terminal 2 — device agent (basic backend, local UI on http://127.0.0.1:8766)
powershell scripts\dev_start_agent.ps1

# 4. pair (either enter the code at http://127.0.0.1:8766, or:)
powershell scripts\pair_agent.ps1 -Code ABCD-1234

# 5. back in http://localhost:8000 — the device is online.
#    Submit: "Open Notepad and type hello from the agent."
#    Watch logs stream; try "Install the new printer driver" to see approvals.
```

CLI equivalents: `python -m agent.main pair --code ABCD-1234 --relay http://localhost:8000`,
`python -m agent.main start [--backend basic|ufo]`, `status`, `unpair`.

Backends: **basic** (default) performs real native Windows actions — open
app, type text, real screenshots — with regex-level "planning"; anything it
can't actually do **fails loudly**. Run it *inside* the desktop session you
are watching, or the input lands on an invisible desktop. **ufo** is the
UFO² integration (milestone 2) for full natural-language tasks.

## How pairing works

Control plane mints a single-use code (`ABCD-1234`, 10 min TTL, also rendered
as a QR encoding `{code, relay_url}`). The agent claims it over HTTPS and
receives a random **device token**, stored under
`%LOCALAPPDATA%\UfoDeviceAgent\state.json`. The agent then connects *outbound*
to `wss://…/ws/device?token=…` and stays connected (reconnect w/ backoff).
Full sequence: [docs/pairing.md](docs/pairing.md).

## Plugging in real UFO²

The integration seam is one class:
[`agent/automation/ufo_backend.py`](agent/automation/ufo_backend.py) — the only
module allowed to import UFO². Install UFO² on a Windows box, wire
`run_instruction` to a UFO session (forwarding step logs through
`emit_log`), and start with `--backend ufo`. Pairing, relay, policy,
approvals, and both UIs are unchanged. Plan: [docs/ufo_integration.md](docs/ufo_integration.md).

## Safety / policy

`policy.yaml` (auto-created in the agent data dir, example in
[examples/policy.yaml](examples/policy.yaml)):

- `blocked_apps` → task denied outright
- `require_approval` risk categories (install_software, delete_files,
  submit_form, purchase, send_email) → task pauses, `approval_required` event
  fires, and the device owner (local UI) **or** operator (dashboard) decides
- `mode: always_ask` → every task needs approval

MVP enforcement is **keyword matching at task intake** — a seatbelt, not a
security boundary. The real upgrade is action-level enforcement via UFO²'s
own sensitive-action confirmations (see integration doc, step 5).

## MCP bridge

```bash
pip install -e ".[mcp]"
python -m agent.mcp_bridge.server_stub   # stdio MCP server
```

Tools: `list_devices`, `get_device_status`, `run_device_task`,
`observe_screen`, `approve_action`, `deny_action`, `pause_device`,
`resume_device`, `get_device_events`. Points at the control plane admin API
(`UFO_CP_URL`, `UFO_CP_ADMIN_TOKEN`). Config example in
[`agent/mcp_bridge/server_stub.py`](agent/mcp_bridge/server_stub.py).

## Auto-update

The packaged `ufo-agent.exe` keeps itself current from GitHub Releases — **no
Python, no reinstall**. Two triggers, both silent (download → verify → restart):

- **On startup**: each `start` checks the `latest` release and self-updates if newer.
- **Operator push**: "⬆ Update agent" in the dashboard (`POST /api/admin/devices/{id}/update`).

How a build becomes an update:

1. Push a tag `vX.Y.Z` → CI builds `ufo-agent.exe`, stamps it with that version,
   and publishes it **plus `ufo-agent.exe.sha256`** to a GitHub Release.
   *(Plain pushes only produce a CI **artifact** — not a Release — so they never trigger updates.)*
2. Agents compare their embedded version to the release tag, download the new
   exe, verify the sha256, **self-test it (`--help`/`status`) before swapping**,
   rename-swap the running binary, relaunch, and reconnect.

Safety: the running exe is never deleted until a verified replacement boots
(rename-first + pre-swap self-test); a target that fails 3× is abandoned
(no boot-loop); only the frozen exe ever acts (source/dev runs are inert).
Disable per-device with `UFO_AGENT_DISABLE_AUTOUPDATE=1`. Integrity is
sha256-vs-published-hash (corruption, not authenticity) — code-signing is the
hardening path. See the design in [the plan](#) / `agent/updater.py`.

## Security

- **Dev posture by default**: localhost, plaintext HTTP/WS, a default admin
  token (`dev-admin-token`). Fine on your machine, nowhere else.
- Device tokens are random (32 bytes) and never in code; pairing codes are
  single-use and expire in 10 minutes.
- Devices connect **outbound only**. No inbound ports, no RDP, no VPN.
- The local UI is loopback-only and is how the agent stays *visible* — there
  is no stealth mode and there never will be.
- Known gaps before any real deployment: TLS everywhere, hash device tokens
  server-side, DPAPI for the local token, real operator auth (the shared
  admin token is a placeholder), rate-limit pairing claims, audit log,
  action-level policy.

## Roadmap

1. ~~Vertical slice with real native actions~~ (this release)
2. Wire `UfoAutomationBackend` to UFO² on Windows (session pump, log
   forwarding, approval bridge, real screenshots)
3. Installer: PyInstaller exe + WinSW/NSSM service + tray app, QR scan pairing
4. Hardening: real auth, hashed tokens, TLS, audit, action-level policy
5. Multi-device orchestration niceties: task queues, artifacts, file transfer

## Repo map

```
agent/            device agent (CLI: python -m agent.main)
  automation/     backend interface, basic native backend, UFO² stub  ← integration seam
  ui/             loopback web dashboard
  windows/        service / user-session worker / tray stubs
  mcp_bridge/     MCP tools over the control plane API
control_plane/    FastAPI: pairing, device relay WS, admin API, web UI
scripts/          dev_start_server / dev_start_agent / pair_agent / install_dev (.ps1)
examples/         policy.yaml, task_examples.json
docs/             architecture, pairing, windows service model, UFO² integration
```

License: MIT. Contributions welcome — especially milestone 2 (UFO² wiring).
