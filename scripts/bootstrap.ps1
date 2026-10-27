# One-time setup on Windows: virtual environment, editable install, environment check, tests.
# Run from the repo root in PowerShell:  .\scripts\bootstrap.ps1
$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot
Set-Location $root

# Find a real Python 3.10+ (the Windows Store stub answers `python` but installs nothing).
$py = $null
foreach ($cand in @("py -3.12", "py -3.11", "py -3", "python3", "python")) {
    try {
        $v = & cmd /c "$cand -c `"import sys; print(sys.version_info[0], sys.version_info[1])`" 2>nul"
        if ($LASTEXITCODE -eq 0 -and $v -match '^\d+ \d+$') {
            $parts = $v.Split(' ')
            if ([int]$parts[0] -eq 3 -and [int]$parts[1] -ge 10) { $py = $cand; break }
        }
    } catch { }
}
if (-not $py) {
    Write-Host "No Python 3.10+ found. Install one, then open a NEW PowerShell window and rerun:"
    Write-Host "    winget install Python.Python.3.12"
    Write-Host "(or python.org, ticking 'Add python.exe to PATH'). 3.12 has wheels for every dependency."
    exit 1
}
Write-Host "Using $py"

if (-not (Test-Path ".venv")) {
    Write-Host "Creating virtual environment in .venv"
    & cmd /c "$py -m venv .venv"
}
& ".\.venv\Scripts\python.exe" -m pip install --upgrade pip --quiet
& ".\.venv\Scripts\python.exe" -m pip install -e ".\python[dev]" -c ".\python\constraints.txt" --quiet   # the pinned, known-working set

Write-Host ""
Write-Host "== ntopjewel doctor =="
& ".\.venv\Scripts\python.exe" -m ntopjewel doctor

Write-Host ""
Write-Host "== offline tests =="
& ".\.venv\Scripts\python.exe" -m pytest ".\python\tests" -q

Write-Host ""
Write-Host "Done. Activate with:  .\.venv\Scripts\Activate.ps1"
