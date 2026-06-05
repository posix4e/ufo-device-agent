# Pair this machine with a control plane using a pairing code.
#
# Usage:
#   powershell scripts/pair_agent.ps1 -Code ABCD-1234
#   powershell scripts/pair_agent.ps1 -Code ABCD-1234 -Relay https://relay.example.com
param(
    [Parameter(Mandatory = $true)][string]$Code,
    [string]$Relay = "http://localhost:8000"
)
$ErrorActionPreference = "Stop"
$repo = Split-Path -Parent $PSScriptRoot
Set-Location $repo

if (-not (Test-Path ".venv")) {
    Write-Host "No .venv found - running scripts/install_dev.ps1 first..."
    & (Join-Path $PSScriptRoot "install_dev.ps1")
}

$py = Join-Path $repo ".venv\Scripts\python.exe"
& $py -m agent.main pair --code $Code --relay $Relay
