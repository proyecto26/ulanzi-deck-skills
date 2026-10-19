<#
.SYNOPSIS
  Windows helper for ulanzi.py: every launchable app as JSON [{name, via, path}].
  via = "lnk" (Start Menu/Desktop shortcut: keeps the working directory, which some apps
  such as OBS need), "appsfolder" (Store/MSIX apps, launched as shell:AppsFolder\<AppID>),
  or "url" (Start entries that are really URLs; use kind "web").
  Writes UTF-8 JSON to -Out (PowerShell 5.1 stdout is not UTF-8, which garbles accented names).
#>
param([Parameter(Mandatory)][string]$Out)
$ErrorActionPreference = 'Stop'
$roots = "$env:APPDATA\Microsoft\Windows\Start Menu\Programs", "$env:ProgramData\Microsoft\Windows\Start Menu\Programs",
         "$env:USERPROFILE\Desktop", "$env:PUBLIC\Desktop"
$lnks = @(Get-ChildItem $roots -Recurse -Filter *.lnk -ErrorAction SilentlyContinue | Where-Object { $_.BaseName -notmatch '^Uninstall' })
$apps = @(Get-StartApps | Where-Object { $_.Name -notmatch '^Uninstall' })
$rows = foreach ($a in $apps) {
  $lnk = $lnks | Where-Object BaseName -eq $a.Name | Select-Object -First 1
  if ($a.AppID -match '^[a-z][a-z0-9+.-]*://') { [pscustomobject]@{ name = $a.Name; via = 'url'; path = $a.AppID } }
  elseif ($lnk) { [pscustomobject]@{ name = $a.Name; via = 'lnk'; path = $lnk.FullName } }
  else { [pscustomobject]@{ name = $a.Name; via = 'appsfolder'; path = "shell:AppsFolder\$($a.AppID)" } }
}
# Some installers only drop a Desktop shortcut and never register a Start entry.
$names = @($apps | ForEach-Object Name)
$rows += $lnks | Where-Object { $_.BaseName -notin $names } | Sort-Object BaseName -Unique |
  ForEach-Object { [pscustomobject]@{ name = $_.BaseName; via = 'lnk'; path = $_.FullName } }
[IO.File]::WriteAllText($Out, (ConvertTo-Json @($rows) -Depth 3 -Compress), (New-Object Text.UTF8Encoding $false))
