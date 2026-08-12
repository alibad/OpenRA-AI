[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)] [int]$ProcessId,
    [Parameter(Mandatory = $true)] [string]$Output,
    [int]$TimeoutSeconds = 45
)

$ErrorActionPreference = "Stop"
Add-Type -AssemblyName System.Drawing
Add-Type @"
using System;
using System.Runtime.InteropServices;
public static class ChinaWindowCapture {
    public delegate bool EnumWindowsProc(IntPtr hWnd, IntPtr lParam);
    [StructLayout(LayoutKind.Sequential)] public struct RECT { public int Left, Top, Right, Bottom; }
    [DllImport("user32.dll")] public static extern bool EnumWindows(EnumWindowsProc callback, IntPtr extra);
    [DllImport("user32.dll")] public static extern uint GetWindowThreadProcessId(IntPtr hWnd, out uint processId);
    [DllImport("user32.dll")] public static extern bool IsWindowVisible(IntPtr hWnd);
    [DllImport("user32.dll")] public static extern bool GetWindowRect(IntPtr hWnd, out RECT rect);
    [DllImport("user32.dll")] public static extern bool SetProcessDPIAware();
}
"@
[void][ChinaWindowCapture]::SetProcessDPIAware()

$deadline = [DateTime]::UtcNow.AddSeconds($TimeoutSeconds)
$window = [IntPtr]::Zero
while ([DateTime]::UtcNow -lt $deadline -and $window -eq [IntPtr]::Zero) {
    [ChinaWindowCapture]::EnumWindows({
        param($handle, $extra)
        [uint32]$owner = 0
        [void][ChinaWindowCapture]::GetWindowThreadProcessId($handle, [ref]$owner)
        if ($owner -eq $ProcessId -and [ChinaWindowCapture]::IsWindowVisible($handle)) {
			$candidate = New-Object ChinaWindowCapture+RECT
			if ([ChinaWindowCapture]::GetWindowRect($handle, [ref]$candidate) -and
				$candidate.Right - $candidate.Left -ge 320 -and $candidate.Bottom - $candidate.Top -ge 240) {
				$script:window = $handle
				return $false
			}
        }
        return $true
    }, [IntPtr]::Zero) | Out-Null
    if ($window -eq [IntPtr]::Zero) { Start-Sleep -Milliseconds 250 }
}

if ($window -eq [IntPtr]::Zero) { throw "No visible OpenRA window was found for PID $ProcessId." }
Start-Sleep -Seconds 8
$rect = New-Object ChinaWindowCapture+RECT
if (-not [ChinaWindowCapture]::GetWindowRect($window, [ref]$rect)) { throw "Could not read the OpenRA window bounds." }
$width = $rect.Right - $rect.Left
$height = $rect.Bottom - $rect.Top
if ($width -lt 320 -or $height -lt 240) { throw "OpenRA window bounds were unexpectedly small: ${width}x${height}." }

$bitmap = New-Object System.Drawing.Bitmap $width, $height
$graphics = [System.Drawing.Graphics]::FromImage($bitmap)
try {
    $graphics.CopyFromScreen($rect.Left, $rect.Top, 0, 0, $bitmap.Size)
    $directory = Split-Path -Parent $Output
    if ($directory) { New-Item -ItemType Directory -Path $directory -Force | Out-Null }
    $bitmap.Save($Output, [System.Drawing.Imaging.ImageFormat]::Png)
}
finally {
    $graphics.Dispose()
    $bitmap.Dispose()
}

Write-Host "Captured OpenRA PID $ProcessId to $Output (${width}x${height})."
