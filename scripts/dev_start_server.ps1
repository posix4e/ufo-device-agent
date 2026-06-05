# Dev launcher for the control plane (FastAPI: pairing + relay + admin UI).
# Serves http://localhost:8000 — admin UI at /, device WS at /ws/device.
#
# NOTE: dev only. For real deployments put this behind TLS (wss://) and set
# UFO_CP_ADMIN_TOKEN to something that is not the default.
$ErrorActionPreference = "Stop"
$repo = Split-Path -Parent $PSScriptRoot
Set-Location $repo

if (-not (Test-Path ".venv")) {
    Write-Host "No .venv found - running scripts/install_dev.ps1 first..."
    & (Join-Path $PSScriptRoot "install_dev.ps1")
}

$py = Join-Path $repo ".venv\Scripts\python.exe"

Write-Host ""
Write-Host "Control plane:  http://localhost:8000"
Write-Host "Admin token:    $(if ($env:UFO_CP_ADMIN_TOKEN) { '(from UFO_CP_ADMIN_TOKEN)' } else { 'dev-admin-token (default, DEV ONLY)' })"
Write-Host ""

& $py -m uvicorn control_plane.main:app --host 127.0.0.1 --port 8000
