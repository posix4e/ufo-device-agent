# Pairing

“Install once. Scan QR. Your AI can now safely use this Windows PC.”

## Protocol

```
Operator                Control plane                    Device agent
   │                         │                                │
   │ POST /api/admin/pairing │                                │
   ├────────────────────────▶│ create code ABCD-1234          │
   │   {code, expires_at,    │ (10 min TTL, single-use)       │
   │    qr_png_url}          │                                │
   │                         │                                │
   │   user reads code / scans QR ─────────────────────────▶  │
   │                         │                                │
   │                         │  POST /api/pairing/claim       │
   │                         │◀───────────────────────────────┤
   │                         │  {code, device_name,           │
   │                         │   install_id}                  │
   │                         │                                │
   │                         │  mint device record + token    │
   │                         ├───────────────────────────────▶│
   │                         │  {device_id, device_token,     │ persist to
   │                         │   relay_ws_url}                │ state.json
   │                         │                                │
   │                         │   WS /ws/device?token=...      │
   │                         │◀═══════════════════════════════┤ outbound only
   │                         │   device_hello, device_status  │
```

## Details

- **Code format**: `XXXX-XXXX` from an alphabet without `0/O/1/I/L`
  (human-readable, speakable over the phone).
- **TTL**: 10 minutes (`PAIRING_TTL_SECONDS`). **Single-use**: the first
  successful claim wins; replays get HTTP 400.
- **QR payload**: `{"v": 1, "code": "ABCD-1234", "relay_url": "https://..."}`
  served as a PNG at `/api/pairing/{code}/qr.png`. The agent's QR *scanner* is
  not implemented yet (manual entry only); the payload format is fixed now so
  a scanner can be added without protocol changes.
- **Claim** is intentionally unauthenticated: the pairing code is the
  credential. Rate-limit it in production.
- **Device token**: 32 random bytes (urlsafe). Stored on the device in
  `state.json` under the app data dir; stored on the control plane in its
  device registry. TODO(production): store only a hash server-side, protect
  the device copy with DPAPI, and move to a keypair + challenge signature.

## Ways to pair

1. **Agent local UI** — open `http://127.0.0.1:8766`, enter code + relay URL.
2. **CLI** — `python -m agent.main pair --code ABCD-1234 --relay http://localhost:8000`
3. **Script** — `powershell scripts/pair_agent.ps1 -Code ABCD-1234`
4. **QR scan** — stubbed; future tray app feature.

`python -m agent.main unpair` forgets the token locally (the control plane
keeps its device record; delete it there separately).
