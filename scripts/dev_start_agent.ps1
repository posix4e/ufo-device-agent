# Dev launcher for the Windows device agent (relay client + local UI + backend).
# Local UI: http://127.0.0.1:8766
#
# Usage:
#   powershell scripts/dev_start_agent.ps1                # basic backend (default, real actions)
#   powershell scripts/dev_start_agent.ps1 -Backend ufo   # once UFO2 is wired up
#
# Production note: this runs everything as one foreground process in your user
# session, which is what GUI automation needs. The eventual installer splits
# this into DeviceAgentService (boot-time supervisor, via pywin32/WinSW/NSSM
# or MSIX services) + DeviceAgentUserWorker (user session) + tray app.
# See docs/windows_service_model.md.
param(
    [string]$Backend = "basic"
)
$ErrorActionPreference = "Stop"
$repo = Split-Path -Parent $PSScriptRoot
Set-Location $repo

if (-not (Test-Path ".venv")) {
    Write-Host "No .venv found - running scripts/install_dev.ps1 first..."
    & (Join-Path $PSScriptRoot "install_dev.ps1")
}

$py = Join-Path $repo ".venv\Scripts\python.exe"
& $py -m agent.main start --backend $Backend
