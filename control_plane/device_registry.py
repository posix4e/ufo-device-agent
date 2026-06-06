"""Device registry: paired devices, recent events, latest status/screenshot.

MVP persistence: devices are saved to a JSON file so pairing survives server
restarts. Events, statuses and screenshots are in-memory only. Swap for
sqlite/Postgres when this grows up.
"""

from __future__ import annotations

import json
import secrets
from collections import deque
from pathlib import Path
from typing import Any

from .models import DeviceRecord, Event, new_uuid, utc_now

MAX_EVENTS_PER_DEVICE = 500


class DeviceRegistry:
    def __init__(self, data_file: Path) -> None:
        self._data_file = data_file
        self._devices: dict[str, DeviceRecord] = {}
        self._by_token: dict[str, str] = {}
        self._events: dict[str, deque[Event]] = {}
        self._last_status: dict[str, dict[str, Any]] = {}
        self._screenshots: dict[str, dict[str, Any]] = {}
        self._load()

    # --- persistence -----------------------------------------------------------

    def _load(self) -> None:
        if not self._data_file.exists():
            return
        raw = json.loads(self._data_file.read_text(encoding="utf-8"))
        for item in raw.get("devices", []):
            rec = DeviceRecord.model_validate(item)
            self._devices[rec.device_id] = rec
            self._by_token[rec.device_token] = rec.device_id

    def _save(self) -> None:
        # NOTE: device tokens in plaintext JSON — dev only. Hash them (store
        # only a digest, compare on connect) before any real deployment.
        self._data_file.parent.mkdir(parents=True, exist_ok=True)
        data = {"devices": [d.model_dump(mode="json") for d in self._devices.values()]}
        self._data_file.write_text(json.dumps(data, indent=2), encoding="utf-8")

    # --- devices ------------------------------------------------------------------

    def register_device(self, device_name: str, install_id: str | None = None) -> DeviceRecord:
        rec = DeviceRecord(
            device_id=new_uuid(),
            device_name=device_name or "unnamed-device",
            device_token=secrets.token_urlsafe(32),
            install_id=install_id,
        )
        self._devices[rec.device_id] = rec
        self._by_token[rec.device_token] = rec.device_id
        self._save()
        return rec

    def get(self, device_id: str) -> DeviceRecord | None:
        return self._devices.get(device_id)

    def by_token(self, token: str) -> DeviceRecord | None:
        device_id = self._by_token.get(token)
        return self._devices.get(device_id) if device_id else None

    def list_devices(self) -> list[DeviceRecord]:
        return list(self._devices.values())

    def remove(self, device_id: str) -> bool:
        """Forget a device entirely: record, token, events, status, screenshot.

        The device keeps its local token until it next tries to connect, at
        which point the relay rejects the now-unknown token (4401) and it must
        be re-paired. Returns False if there was no such device.
        """
        rec = self._devices.pop(device_id, None)
        if rec is None:
            return False
        self._by_token.pop(rec.device_token, None)
        self._events.pop(device_id, None)
        self._last_status.pop(device_id, None)
        self._screenshots.pop(device_id, None)
        self._save()
        return True

    def touch(self, device_id: str) -> None:
        rec = self._devices.get(device_id)
        if rec:
            rec.last_seen = utc_now()

    # --- status / events / screenshots ------------------------------------------------

    def set_last_status(self, device_id: str, status: dict[str, Any]) -> None:
        self._last_status[device_id] = status

    def last_status(self, device_id: str) -> dict[str, Any] | None:
        return self._last_status.get(device_id)

    def add_event(self, device_id: str, type_: str, payload: dict[str, Any]) -> Event:
        event = Event(device_id=device_id, type=type_, payload=payload)
        self._events.setdefault(device_id, deque(maxlen=MAX_EVENTS_PER_DEVICE)).append(event)
        return event

    def events(self, device_id: str, limit: int = 100) -> list[Event]:
        return list(self._events.get(device_id, []))[-limit:]

    def set_screenshot(self, device_id: str, data: dict[str, Any]) -> None:
        self._screenshots[device_id] = data

    def get_screenshot(self, device_id: str) -> dict[str, Any] | None:
        return self._screenshots.get(device_id)
