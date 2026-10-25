# One-time setup on Windows: virtual environment, editable install, environment check, tests.
# Run from the repo root in PowerShell:  .\scripts\bootstrap.ps1
$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot
Set-Location $root

if (-not (Test-Path ".venv")) {
    Write-Host "Creating virtual environment in .venv"
    python -m venv .venv
}
& ".\.venv\Scripts\python.exe" -m pip install --upgrade pip --quiet
& ".\.venv\Scripts\python.exe" -m pip install -e ".\python[dev]" --quiet

Write-Host ""
Write-Host "== ntopjewel doctor =="
& ".\.venv\Scripts\python.exe" -m ntopjewel doctor

Write-Host ""
Write-Host "== offline tests =="
& ".\.venv\Scripts\python.exe" -m pytest ".\python\tests" -q

Write-Host ""
Write-Host "Done. Activate with:  .\.venv\Scripts\Activate.ps1"
