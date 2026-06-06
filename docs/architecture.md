# Architecture

```
                         ┌────────────────────────────────────────────┐
                         │            Control plane (FastAPI)         │
                         │                                            │
  Operator / AI agent ──▶│  admin API (/api/admin/*)   admin web UI   │
  (MCP bridge, curl,     │  pairing (/api/pairing/*)                  │
   web UI)               │  device relay (/ws/device)  device registry│
                         └───────────────▲────────────────────────────┘
                                         │ outbound WebSocket only
                                         │ (wss://, token auth)
                         ┌───────────────┴────────────────────────────┐
                         │        Windows device agent (one process   │
                         │        in MVP; three in production)        │
                         │                                            │
                         │  relay_client ──▶ task_runner ──▶ backend  │
                         │       ▲               │   ▲                │
                         │       │            policy  │               │
                         │  local web UI ◀───────────┘                │
                         │  (127.0.0.1:8766, approve/deny/pause)      │
                         └────────────────────────────────────────────┘
                                              │
                                   BasicAutomationBackend (default: real
                                     native open/type/screenshot, no planning)
                                   UfoAutomationBackend  → Microsoft UFO²
```

## Components

### Control plane (`control_plane/`)
- **pairing.py** — short-lived, single-use pairing codes; the unauthenticated
  claim endpoint exchanges a code for a device token; QR PNG endpoint.
- **relay.py** — one WebSocket per device (`/ws/device?token=...`). Records
  inbound device events; pushes operator commands down the same socket.
- **device_registry.py** — paired devices (JSON-persisted), recent events,
  last status, latest screenshot (in-memory).
- **admin_api.py** — operator HTTP API guarded by a single dev token.
- **static/index.html** — admin web UI (pairing, device list, tasks, events,
  approvals, screenshots).

### Device agent (`agent/`)
- **relay_client.py** — outbound-only WebSocket with reconnect/backoff and
  heartbeats. Dispatches relay messages to the task runner.
- **task_runner.py** — the pipeline: policy check → (approval wait) →
  backend execution → event emission. Also the shared runtime state
  (paused, current task, recent logs, pending approvals). Tasks are serial.
- **policy.py** — YAML policy, keyword-matched at task intake (MVP).
- **automation/** — backend interface + basic native backend + UFO² stub.
  The *only* layer that touches the GUI; backends do real work or fail
  loudly. `ufo_backend.py` is the single module allowed to import UFO².
- **ui/local_server.py** — loopback-only web UI: status, logs, pause/resume,
  approve/deny, and pairing.
- **identity.py / storage.py** — local identity, pairing claim, app-data
  persistence (`%LOCALAPPDATA%\UfoDeviceAgent`).
- **windows/** — production process-model stubs (service / user worker / tray).
- **mcp_bridge/** — MCP tools backed by the control plane admin API.

## Message protocol

JSON frames over WebSocket: `{"type": "<type>", "payload": {...}}`.

| Direction | Type | Payload (key fields) |
|---|---|---|
| device → relay | `device_hello` | device_name, agent_version, backend |
| device → relay | `device_status` | paused, current_task, pending_approvals (heartbeat; not event-logged) |
| device → relay | `task_started` | task_id, instruction |
| device → relay | `task_log` | task_id, message |
| device → relay | `task_completed` | TaskResult |
| device → relay | `task_failed` | TaskResult (also used for policy/user denials) |
| device → relay | `approval_required` | task_id, instruction, reason |
| device → relay | `screenshot_available` | description, screenshot_b64, captured_at |
| relay → device | `run_task` | Task object |
| relay → device | `observe_screen` | — |
| relay → device | `approve_action` / `deny_action` | task_id |
| relay → device | `pause` / `resume` | — |
| relay → device | `update_policy` | (received but not applied in MVP — see TODO in relay_client.py) |

Task and result objects are defined in `agent/models.py` (`Task`, `TaskResult`).

## Trust model (MVP)

- The device trusts the control plane it paired with; the device token is the
  credential and rides the query string of the WS URL (fine over TLS in dev;
  move to a header/first-frame auth later).
- Raw UFO²/automation is never network-exposed; the only network surface on
  the device is the *outbound* WS client plus a loopback-only local UI.
- The admin API is a single shared token — explicitly not production auth.
- Approvals can come from the device owner (local UI) or the operator
  (admin API); either resolves the same pending approval.
