# Run this INSIDE your interactive Windows session (your RDP window), not over
# SSH — GUI automation needs a visible desktop.
#
# It asks the control plane for a fresh pairing code, claims it, then starts
# the agent in this session so launched apps actually appear on screen.
#
# Usage (from the folder holding ufo-agent.exe):
#   powershell -ExecutionPolicy Bypass -File scripts\demo_pair_and_start.ps1 `
#       -Relay http://100.115.205.26:8000 -AdminToken <token> -Exe C:\Users\bambu\ufo-agent.exe
param(
    [Parameter(Mandatory = $true)][string]$Relay,
    [Parameter(Mandatory = $true)][string]$AdminToken,
    [string]$Exe = "C:\Users\bambu\ufo-agent.exe"
)
$ErrorActionPreference = "Stop"

Write-Host "Requesting a pairing code from $Relay ..."
$code = (Invoke-RestMethod -Method Post -Uri "$Relay/api/admin/pairing" `
    -Headers @{ "X-Admin-Token" = $AdminToken }).code
Write-Host "Pairing code: $code"

& $Exe unpair | Out-Null
& $Exe pair --code $code --relay $Relay
if ($LASTEXITCODE -ne 0) { throw "pairing failed" }

Write-Host ""
Write-Host "Starting agent in THIS session. Submit a task from the dashboard"
Write-Host "($Relay) and watch it happen on this desktop. Ctrl+C to stop."
Write-Host ""
& $Exe start
