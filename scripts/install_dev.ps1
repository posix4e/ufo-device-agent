# One-time dev setup: create a venv and install the project (editable).
#
# Requires Python 3.11+ on PATH (https://www.python.org/downloads/ - check
# "Add python.exe to PATH" in the installer). End users will NOT need this:
# production packaging bundles Python via PyInstaller/MSIX.
$ErrorActionPreference = "Stop"
$repo = Split-Path -Parent $PSScriptRoot
Set-Location $repo

# Prefer the py launcher if available, fall back to python.
$bootstrap = if (Get-Command py -ErrorAction SilentlyContinue) { "py" } else { "python" }

Write-Host "Creating virtualenv (.venv) with $bootstrap ..."
& $bootstrap -m venv .venv

$py = Join-Path $repo ".venv\Scripts\python.exe"
& $py -m pip install --upgrade pip
& $py -m pip install -e ".[dev]"

Write-Host ""
Write-Host "Done. Next:"
Write-Host "  powershell scripts/dev_start_server.ps1     # terminal 1: control plane"
Write-Host "  powershell scripts/dev_start_agent.ps1      # terminal 2: device agent"
Write-Host "  then open http://localhost:8000 and create a pairing code."
