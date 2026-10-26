# One-time setup for nTop's Python Console over SSH (Notebook API, Private Beta), per nTop's
# Notebook API documentation: an ed25519 key at ~\.ssh\id_ntopcli, its public half appended
# to ~\.ssh\authorized_keys as plain ASCII (no BOM), both files readable by this account only,
# and the Documents\nTopScripts folder nTop looks in for user scripts.
#
#   .\scripts\setup-ntop-console.ps1
#   # then open nTop, View > Python Console, and:
#   python -m ntopjewel api check
$ErrorActionPreference = "Stop"

$sshDir = Join-Path $HOME ".ssh"
$key = Join-Path $sshDir "id_ntopcli"
$auth = Join-Path $sshDir "authorized_keys"

if (-not (Test-Path $sshDir)) { New-Item -ItemType Directory -Path $sshDir | Out-Null }

if (-not (Get-Command ssh-keygen -ErrorAction SilentlyContinue)) {
    Write-Host "ssh-keygen not found. Install the OpenSSH client: Settings > Apps > Optional features > OpenSSH Client" -ForegroundColor Yellow
    exit 1
}

if (-not (Test-Path $key)) {
    # An empty passphrase: the key only ever reaches localhost:2222 and the file is owner-only.
    if ($PSVersionTable.PSVersion.Major -ge 7) { ssh-keygen -t ed25519 -f $key -N "" -C "nTop console key" }
    else { ssh-keygen -t ed25519 -f $key -N '""' -C "nTop console key" }
    if ($LASTEXITCODE -ne 0) { throw "ssh-keygen failed" }
    Write-Host "created $key"
} else {
    Write-Host "key exists: $key"
}

$pub = (Get-Content "$key.pub" -Raw).Trim()
$existing = if (Test-Path $auth) { (Get-Content $auth -Raw) } else { "" }
if ($existing -notlike "*$pub*") {
    $content = if ($existing.Trim()) { $existing.TrimEnd() + "`n" + $pub + "`n" } else { $pub + "`n" }
    # ASCII without a byte-order mark: nTop's server ignores a file that starts with a BOM.
    [System.IO.File]::WriteAllText($auth, $content, [System.Text.Encoding]::ASCII)
    Write-Host "appended the public key to $auth"
} else {
    Write-Host "authorized_keys already holds the key"
}

# owner-only: the server refuses keys other accounts could edit
foreach ($f in @($key, $auth)) {
    icacls $f /inheritance:r /grant:r "${env:USERNAME}:(R,W)" | Out-Null
}

$scripts = Join-Path $HOME "Documents\nTopScripts"
if (-not (Test-Path $scripts)) { New-Item -ItemType Directory -Path $scripts | Out-Null; Write-Host "created $scripts" }

Write-Host ""
Write-Host "Done. Open nTop (with any notebook), View > Python Console, then:"
Write-Host "    python -m ntopjewel api check"
Write-Host "    python -m ntopjewel api build band_profile"
