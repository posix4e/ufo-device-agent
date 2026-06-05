"""Device identity + pairing-code claim.

MVP flow: the agent generates a random install id and secret locally, then
exchanges a short-lived pairing code for a server-issued device token over
HTTPS (HTTP in dev). The token is the device's credential for the relay.

TODO(production): replace the random secret with a real keypair (e.g. Ed25519)
and sign a server challenge during pairing, so a stolen token can be rotated
without re-pairing and the transport doesn't have to be the only protection.
"""

from __future__ import annotations

import secrets
import uuid

import httpx

from .storage import AgentState, AgentStorage


class PairingError(RuntimeError):
    pass


def ensure_local_identity(state: AgentState, device_name: str) -> AgentState:
    if not state.install_id:
        state.install_id = str(uuid.uuid4())
    if not state.device_secret:
        state.device_secret = secrets.token_urlsafe(32)
    if not state.device_name:
        state.device_name = device_name
    return state


async def claim_pairing_code(
    storage: AgentStorage,
    state: AgentState,
    *,
    code: str,
    relay_url: str,
    device_name: str,
) -> AgentState:
    """Exchange a pairing code for a device token and persist the result."""
    ensure_local_identity(state, device_name)
    relay_url = relay_url.rstrip("/")
    try:
        async with httpx.AsyncClient(timeout=15) as client:
            resp = await client.post(
                f"{relay_url}/api/pairing/claim",
                json={
                    "code": code.strip().upper(),
                    "device_name": state.device_name,
                    "install_id": state.install_id,
                },
            )
    except httpx.HTTPError as exc:
        raise PairingError(f"could not reach control plane at {relay_url}: {exc}") from exc

    if resp.status_code != 200:
        try:
            detail = resp.json().get("detail", resp.text)
        except ValueError:
            detail = resp.text
        raise PairingError(f"pairing claim failed ({resp.status_code}): {detail}")

    data = resp.json()
    state.device_id = data["device_id"]
    state.device_token = data["device_token"]
    state.relay_url = relay_url
    state.relay_ws_url = data["relay_ws_url"]
    storage.save_state(state)
    return state
