<#
.SYNOPSIS
  Download the latest Ulanzi Studio for Windows from Ulanzi's CDN, verify its Authenticode
  signature, and (with -Install) run the silent NSIS install.
.DESCRIPTION
  The www host (www.ulanzistudio.com) has returned 504s; the bare host redirects (302)
  to cdn.ulanzistudio.com/UlanziDeck/<ver>/Win_Ulanzi_Studio_V<ver>.<date>.exe.
  Without -Install it only downloads + verifies, so you can tell the user the version first.
.EXAMPLE
  powershell -NoProfile -ExecutionPolicy Bypass -File install.ps1            # download + verify; version is in FILE's name
  powershell -NoProfile -ExecutionPolicy Bypass -File install.ps1 -Install   # ...then install silently (/S)
#>
param([string]$DownloadDir = (Join-Path $env:TEMP ('ulanzi-install-' + (Get-Date -Format 'yyyyMMdd_HHmmss'))), [switch]$Install)
$ErrorActionPreference = 'Stop'
$url = (& curl.exe -s -o NUL -w '%{redirect_url}' -A 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)' --max-time 60 'https://ulanzistudio.com/deck/download/windows')
if ($url -notmatch '^https://cdn\.ulanzistudio\.com/.+\.exe$') { throw "Unexpected download redirect: '$url'. Check https://www.ulanzi.com/pages/ulanzi-app manually." }
New-Item -ItemType Directory -Force $DownloadDir | Out-Null
$file = Join-Path $DownloadDir (Split-Path $url -Leaf)
& curl.exe -fL -s -A 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)' --max-time 1200 -o $file $url
if ($LASTEXITCODE) { throw "Download failed ($LASTEXITCODE)" }
$sig = Get-AuthenticodeSignature $file
"FILE      : $file ($([math]::Round((Get-Item $file).Length / 1MB)) MB)"
"SIGNATURE: $($sig.Status) | $($sig.SignerCertificate.Subject -replace ',.*$', '')"
# Anchor on the subject's CN: the name appearing in an OU or another field must not pass.
if ($sig.Status -ne 'Valid' -or $sig.SignerCertificate.Subject -notmatch '^CN="?Shenzhen Ulanzi Technology Co\., Ltd\."?,') { throw 'Signature is not a valid Shenzhen Ulanzi Technology signature. Do not run this file.' }
if (-not $Install) { "Verified. Re-run with -Install to install."; return }
Get-Process UlanziDeck -ErrorAction SilentlyContinue | Stop-Process -Force
$p = Start-Process -FilePath $file -ArgumentList '/S' -Wait -PassThru
"EXITCODE : $($p.ExitCode)"
Get-ItemProperty HKLM:\Software\WOW6432Node\Microsoft\Windows\CurrentVersion\Uninstall\*, HKLM:\Software\Microsoft\Windows\CurrentVersion\Uninstall\* -ErrorAction SilentlyContinue |
  Where-Object { $_.DisplayName -match '^Ulanzi Studio' } | ForEach-Object { "INSTALLED: $($_.DisplayName) $($_.DisplayVersion)" }
