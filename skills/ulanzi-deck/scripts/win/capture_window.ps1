<#
.SYNOPSIS
  Save a PNG of the Ulanzi Studio window so the result can be shown in chat with Read.
  Uses PrintWindow(PW_RENDERFULLCONTENT), which renders the window even when other windows
  cover it (screen-copy approaches capture whatever is on top, because Windows often
  refuses SetForegroundWindow from a background process). Prints the PNG path.
.EXAMPLE
  powershell -NoProfile -ExecutionPolicy Bypass -File capture_window.ps1 -Out "$env:TEMP\ulanzi_window.png"
#>
param([string]$Out = (Join-Path $env:TEMP 'ulanzi_window.png'))
$ErrorActionPreference = 'Stop'
if (-not ('UlzWin' -as [type])) {
Add-Type @"
using System; using System.Runtime.InteropServices;
public static class UlzWin {
  [DllImport("user32.dll")] public static extern bool IsIconic(IntPtr h);
  [DllImport("user32.dll")] public static extern bool ShowWindow(IntPtr h, int n);
  [DllImport("user32.dll")] public static extern bool GetWindowRect(IntPtr h, out RECT r);
  [DllImport("user32.dll")] public static extern bool PrintWindow(IntPtr h, IntPtr hdc, uint flags);
  [DllImport("user32.dll")] public static extern bool SetProcessDPIAware();
  [StructLayout(LayoutKind.Sequential)] public struct RECT { public int L, T, R, B; }
}
"@
}
Add-Type -AssemblyName System.Drawing
[UlzWin]::SetProcessDPIAware() | Out-Null
$p = Get-Process UlanziDeck -ErrorAction SilentlyContinue | Where-Object { $_.MainWindowHandle -ne 0 } | Select-Object -First 1
if (-not $p) { throw 'Ulanzi Studio has no window handle (not running, or closed to the tray: launch UlanziDeck.exe again to reopen it).' }
$h = $p.MainWindowHandle
if ([UlzWin]::IsIconic($h)) { [UlzWin]::ShowWindow($h, 9) | Out-Null; Start-Sleep -Milliseconds 800 }
$r = New-Object UlzWin+RECT; [UlzWin]::GetWindowRect($h, [ref]$r) | Out-Null
$bmp = New-Object System.Drawing.Bitmap ($r.R - $r.L), ($r.B - $r.T)
$g = [System.Drawing.Graphics]::FromImage($bmp); $hdc = $g.GetHdc()
$ok = [UlzWin]::PrintWindow($h, $hdc, 2)   # 2 = PW_RENDERFULLCONTENT (needed for Qt/GPU-drawn windows)
$g.ReleaseHdc($hdc); $g.Dispose()
if (-not $ok) { throw 'PrintWindow failed.' }
$bmp.Save($Out, [System.Drawing.Imaging.ImageFormat]::Png); $bmp.Dispose()
$Out
