<#
.SYNOPSIS
  Windows helper for ulanzi.py: export shell icons (exe, .lnk, shell:AppsFolder\<AppID>) as
  PNG with alpha, in one batch so the C# shim is compiled once.
.PARAMETER Jobs
  JSON file: [{"src": "<path or shell:AppsFolder\\AppID>", "out": "<png path>"}, ...]
#>
param([Parameter(Mandatory)][string]$Jobs, [Parameter(Mandatory)][string]$Out, [int]$Size = 256)
$ErrorActionPreference = 'Stop'
Add-Type -AssemblyName System.Drawing
Add-Type -ReferencedAssemblies System.Drawing -TypeDefinition @"
using System;
using System.Drawing;
using System.Drawing.Imaging;
using System.Runtime.InteropServices;
public static class UlzShellIcon {
  [ComImport, Guid("bcc18b79-ba16-442f-80c4-8a59c30c463b"), InterfaceType(ComInterfaceType.InterfaceIsIUnknown)]
  private interface IShellItemImageFactory { [PreserveSig] int GetImage(SIZE size, int flags, out IntPtr phbm); }
  [StructLayout(LayoutKind.Sequential)] private struct SIZE { public int cx; public int cy; }
  [DllImport("shell32.dll", CharSet = CharSet.Unicode)]
  private static extern int SHCreateItemFromParsingName(string path, IntPtr pbc, ref Guid riid, out IShellItemImageFactory ppv);
  [DllImport("gdi32.dll")] private static extern bool DeleteObject(IntPtr h);
  public static Bitmap Get(string path, int size) {
    Guid iid = new Guid("bcc18b79-ba16-442f-80c4-8a59c30c463b");
    IShellItemImageFactory f;
    int hr = SHCreateItemFromParsingName(path, IntPtr.Zero, ref iid, out f);
    if (hr != 0) Marshal.ThrowExceptionForHR(hr);
    SIZE s; s.cx = size; s.cy = size;
    IntPtr hb;
    hr = f.GetImage(s, 0x4 /* SIIGBF_ICONONLY */, out hb);
    if (hr != 0) Marshal.ThrowExceptionForHR(hr);
    try {
      Bitmap src = Image.FromHbitmap(hb);
      if (Image.GetPixelFormatSize(src.PixelFormat) < 32) return src;
      // FromHbitmap drops alpha; re-wrap the raw 32bpp bits as ARGB to keep transparency.
      Rectangle r = new Rectangle(0, 0, src.Width, src.Height);
      BitmapData bd = src.LockBits(r, ImageLockMode.ReadOnly, src.PixelFormat);
      Bitmap tmp = new Bitmap(bd.Width, bd.Height, bd.Stride, PixelFormat.Format32bppArgb, bd.Scan0);
      Bitmap outb = new Bitmap(tmp.Width, tmp.Height, PixelFormat.Format32bppArgb);
      using (Graphics g = Graphics.FromImage(outb)) { g.DrawImage(tmp, new Rectangle(0, 0, tmp.Width, tmp.Height)); }
      src.UnlockBits(bd); tmp.Dispose(); src.Dispose();
      return outb;
    } finally { DeleteObject(hb); }
  }
}
"@
$results = foreach ($j in (Get-Content $Jobs -Raw -Encoding UTF8 | ConvertFrom-Json)) {
  try {
    $bmp = [UlzShellIcon]::Get($j.src, $Size); $bmp.Save($j.out, [System.Drawing.Imaging.ImageFormat]::Png); $bmp.Dispose()
    [pscustomobject]@{ src = $j.src; out = $j.out; ok = $true }
  } catch { [pscustomobject]@{ src = $j.src; out = $j.out; ok = $false; error = $_.Exception.Message } }
}
# Results go to a UTF-8 file: PowerShell 5.1 stdout is not UTF-8.
[IO.File]::WriteAllText($Out, (ConvertTo-Json @($results) -Depth 3 -Compress), (New-Object Text.UTF8Encoding $false))
