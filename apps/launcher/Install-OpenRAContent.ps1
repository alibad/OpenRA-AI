[CmdletBinding()]
param(
    [string]$MirrorList = "https://www.openra.net/packages/ra-quickinstall-mirrors.txt",
    [switch]$KeepDownload
)

$ErrorActionPreference = "Stop"
$expectedSha1 = "44241f68e69db9511db82cf83c174737ccda300b"
$supportRoot = Join-Path $env:APPDATA "OpenRA"
$contentRoot = Join-Path $supportRoot "Content\ra\v2"
$requiredFiles = @(
    "allies.mix",
    "conquer.mix",
    "interior.mix",
    "hires.mix",
    "lores.mix",
    "local.mix",
    "speech.mix",
    "russian.mix",
    "snow.mix",
    "sounds.mix",
    "temperat.mix",
    "expand\expand2.mix",
    "expand\hires1.mix",
    "expand\lores1.mix",
    "cnc\desert.mix"
)

function Test-ContentInstalled {
    return @($requiredFiles | Where-Object { -not (Test-Path -LiteralPath (Join-Path $contentRoot $_)) }).Count -eq 0
}

if (Test-ContentInstalled) {
    Write-Host "OpenRA Red Alert content is already installed." -ForegroundColor Green
    return
}

Write-Host "Installing OpenRA's supported Red Alert quick-install content..." -ForegroundColor Cyan
Write-Host "This package is sourced from OpenRA's mirrors of the 2008 freeware release."

$downloadDirectory = Join-Path $env:TEMP "OpenRA-AI"
$downloadPath = Join-Path $downloadDirectory "ra-quickinstall.zip"
New-Item -ItemType Directory -Path $downloadDirectory -Force | Out-Null

$mirrorsResponse = Invoke-WebRequest -UseBasicParsing -Uri $MirrorList -TimeoutSec 20
$mirrors = @($mirrorsResponse.Content -split "`r?`n" | ForEach-Object { $_.Trim() } | Where-Object { $_ -match "^https://" })
if ($mirrors.Count -eq 0) {
    throw "OpenRA did not return any HTTPS quick-install mirrors."
}

$downloadValid = $false
if (Test-Path -LiteralPath $downloadPath) {
    $downloadValid = (Get-FileHash -LiteralPath $downloadPath -Algorithm SHA1).Hash.ToLowerInvariant() -eq $expectedSha1
}

foreach ($mirror in $mirrors) {
    if ($downloadValid) {
        break
    }

    try {
        Invoke-WebRequest -UseBasicParsing -Uri $mirror -OutFile $downloadPath -TimeoutSec 120
        $downloadValid = (Get-FileHash -LiteralPath $downloadPath -Algorithm SHA1).Hash.ToLowerInvariant() -eq $expectedSha1
    }
    catch {
        $downloadValid = $false
    }
}

if (-not $downloadValid) {
    throw "Unable to download a checksum-valid OpenRA Red Alert quick-install package."
}

Add-Type -AssemblyName System.IO.Compression.FileSystem
$supportResolved = [IO.Path]::GetFullPath($supportRoot)
$contentResolved = [IO.Path]::GetFullPath($contentRoot)
if (-not $contentResolved.StartsWith($supportResolved + [IO.Path]::DirectorySeparatorChar)) {
    throw "Refusing to install content outside the OpenRA support directory."
}

New-Item -ItemType Directory -Path $contentResolved -Force | Out-Null
$archive = [IO.Compression.ZipFile]::OpenRead($downloadPath)
try {
    foreach ($entry in $archive.Entries) {
        if ([IO.Path]::IsPathRooted($entry.FullName) -or $entry.FullName -match "(^|[\\/])\.\.([\\/]|$)") {
            throw "The downloaded archive contains an unsafe path."
        }

        $destination = [IO.Path]::GetFullPath((Join-Path $contentResolved $entry.FullName))
        if (-not $destination.StartsWith($contentResolved + [IO.Path]::DirectorySeparatorChar)) {
            throw "The downloaded archive would write outside the OpenRA content directory."
        }

        if ([string]::IsNullOrEmpty($entry.Name)) {
            New-Item -ItemType Directory -Path $destination -Force | Out-Null
            continue
        }

        New-Item -ItemType Directory -Path ([IO.Path]::GetDirectoryName($destination)) -Force | Out-Null
        [IO.Compression.ZipFileExtensions]::ExtractToFile($entry, $destination, $true)
    }
}
finally {
    $archive.Dispose()
}

if (-not (Test-ContentInstalled)) {
    throw "OpenRA content installation completed but required files are still missing."
}

if (-not $KeepDownload -and (Test-Path -LiteralPath $downloadPath)) {
    $downloadResolved = (Resolve-Path -LiteralPath $downloadPath).Path
    $tempResolved = (Resolve-Path -LiteralPath $env:TEMP).Path
    if ($downloadResolved.StartsWith($tempResolved + [IO.Path]::DirectorySeparatorChar)) {
        Remove-Item -LiteralPath $downloadResolved
    }
}

Write-Host "OpenRA Red Alert content is ready." -ForegroundColor Green
