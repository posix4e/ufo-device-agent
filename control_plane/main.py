"""Control plane app: pairing + device relay + admin API + static admin UI.

Dev run:
    uvicorn control_plane.main:app --port 8000
    (or: powershell scripts/dev_start_server.ps1)

Env:
    UFO_CP_ADMIN_TOKEN  admin API token        (default: dev-admin-token — DEV ONLY)
    UFO_CP_DATA_DIR     persistence directory  (default: ./control_plane_data)
    UFO_CP_PUBLIC_URL   public base URL agents use, when behind a proxy/tunnel
"""

from __future__ import annotations

import os
from pathlib import Path

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from .admin_api import DEV_ADMIN_TOKEN
from .admin_api import router as admin_router
from .device_registry import DeviceRegistry
from .pairing import PairingManager
from .pairing import router as pairing_router
from .relay import ConnectionManager
from .relay import router as relay_router

STATIC_DIR = Path(__file__).parent / "static"


def create_app() -> FastAPI:
    app = FastAPI(title="UFO Device Agent — Control Plane", version="0.1.0")

    data_dir = Path(os.environ.get("UFO_CP_DATA_DIR", "./control_plane_data"))
    app.state.registry = DeviceRegistry(data_dir / "devices.json")
    app.state.pairing = PairingManager()
    app.state.connections = ConnectionManager()

    app.include_router(pairing_router)
    app.include_router(relay_router)
    app.include_router(admin_router)

    # Static admin UI at / — mounted last so API routes win.
    app.mount("/", StaticFiles(directory=STATIC_DIR, html=True), name="static")

    if DEV_ADMIN_TOKEN == "dev-admin-token":
        print("WARNING: using default dev admin token. Set UFO_CP_ADMIN_TOKEN for anything beyond localhost.")

    return app


app = create_app()
