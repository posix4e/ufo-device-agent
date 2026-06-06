"""Pairing codes: short-lived, single-use, human-typable.

Flow (see docs/pairing.md):
    operator creates code -> user enters it (or scans the QR) in the agent ->
    agent POSTs /api/pairing/claim -> control plane mints a device token.

The claim endpoint is unauthenticated on purpose: the pairing code IS the
credential. Codes expire (10 min) and are single-use.
"""

from __future__ import annotations

import io
import json
import os
import secrets
from datetime import timedelta

import qrcode
from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import Response

from .models import ClaimRequest, ClaimResponse, PairingCodeInfo, utc_now

# No 0/O/1/I/L — codes get read aloud and typed by humans.
CODE_ALPHABET = "ABCDEFGHJKMNPQRSTUVWXYZ23456789"
PAIRING_TTL_SECONDS = 600


class PairingClaimError(Exception):
    pass


class PairingManager:
    def __init__(self, ttl_seconds: int = PAIRING_TTL_SECONDS) -> None:
        self.ttl_seconds = ttl_seconds
        self._codes: dict[str, PairingCodeInfo] = {}

    def create_code(self) -> PairingCodeInfo:
        code = "-".join("".join(secrets.choice(CODE_ALPHABET) for _ in range(4)) for _ in range(2))
        info = PairingCodeInfo(code=code, expires_at=utc_now() + timedelta(seconds=self.ttl_seconds))
        self._codes[code] = info
        return info

    def claim(self, code: str) -> PairingCodeInfo:
        info = self._codes.get(code.strip().upper())
        if info is None:
            raise PairingClaimError("unknown pairing code")
        if info.claimed_by is not None:
            raise PairingClaimError("pairing code already claimed")
        if utc_now() > info.expires_at:
            raise PairingClaimError("pairing code expired")
        return info

    def mark_claimed(self, code: str, device_id: str) -> None:
        info = self._codes.get(code)
        if info:
            info.claimed_by = device_id


# --- HTTP routes -----------------------------------------------------------------


router = APIRouter()


def _public_base_url(request: Request) -> str:
    """Base URL agents should use to reach this server.

    Behind a reverse proxy / tunnel, set UFO_CP_PUBLIC_URL (e.g.
    https://relay.example.com); otherwise the request's own base URL is used.
    """
    return (os.environ.get("UFO_CP_PUBLIC_URL") or str(request.base_url)).rstrip("/")


def _device_ws_url(request: Request) -> str:
    base = _public_base_url(request)
    ws_base = base.replace("https://", "wss://", 1).replace("http://", "ws://", 1)
    return f"{ws_base}/ws/device"


@router.post("/api/pairing/claim", response_model=ClaimResponse)
async def claim_pairing_code(req: ClaimRequest, request: Request) -> ClaimResponse:
    pairing: PairingManager = request.app.state.pairing
    registry = request.app.state.registry
    try:
        info = pairing.claim(req.code)
    except PairingClaimError as exc:
        raise HTTPException(status_code=400, detail=str(exc))

    device = registry.register_device(req.device_name, req.install_id)
    pairing.mark_claimed(info.code, device.device_id)
    registry.add_event(device.device_id, "paired", {"device_name": device.device_name})

    return ClaimResponse(
        device_id=device.device_id,
        device_token=device.device_token,
        relay_ws_url=_device_ws_url(request),
    )


@router.get("/api/pairing/{code}/qr.png")
async def pairing_qr(code: str, request: Request) -> Response:
    """QR image encoding {v, code, relay_url} — what a future agent QR scanner reads.

    NOTE: unauthenticated for dev convenience; the code itself is the secret
    and expires in 10 minutes.
    """
    payload = json.dumps({"v": 1, "code": code.strip().upper(), "relay_url": _public_base_url(request)})
    img = qrcode.make(payload)
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return Response(content=buf.getvalue(), media_type="image/png")
