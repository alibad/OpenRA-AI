[CmdletBinding()]
param([string]$Version = "0.1.0-alpha.1")

$ErrorActionPreference = "Stop"
$repositoryRoot = Split-Path -Parent $PSScriptRoot
$artifactRoot = Join-Path $repositoryRoot "artifacts"
$packageRoot = Join-Path $artifactRoot "package\windows-x64"
$releaseRoot = Join-Path $artifactRoot "releases"
$releaseName = "OpenRA-AI-$Version-windows-x64"
$stageRoot = Join-Path $packageRoot $releaseName
$releaseArchive = Join-Path $releaseRoot "$releaseName.zip"
$python = Join-Path $repositoryRoot ".venv\Scripts\python.exe"
$engineRoot = Join-Path $repositoryRoot "engine\openra"
$dotnetRoot = Join-Path $env:USERPROFILE ".dotnet"

if (-not (Test-Path -LiteralPath $python)) {
    throw "Python environment is missing. Run scripts\setup.ps1 first."
}

New-Item -ItemType Directory -Path $artifactRoot -Force | Out-Null
if (Test-Path -LiteralPath $packageRoot) {
    $packageResolved = (Resolve-Path -LiteralPath $packageRoot).Path
    $artifactResolved = (Resolve-Path -LiteralPath $artifactRoot).Path
    if (-not $packageResolved.StartsWith($artifactResolved + [IO.Path]::DirectorySeparatorChar)) {
        throw "Refusing to replace a package directory outside artifacts."
    }
    Remove-Item -LiteralPath $packageResolved -Recurse
}
New-Item -ItemType Directory -Path $stageRoot -Force | Out-Null
New-Item -ItemType Directory -Path $releaseRoot -Force | Out-Null

$enginePosix = (& "C:\Program Files\Git\usr\bin\cygpath.exe" -u $engineRoot).Trim()
$stagePosix = (& "C:\Program Files\Git\usr\bin\cygpath.exe" -u $stageRoot).Trim()
$dotnetPosix = (& "C:\Program Files\Git\usr\bin\cygpath.exe" -u $dotnetRoot).Trim()
$packageCommand = @"
set -e
export PATH='$dotnetPosix':`$PATH
source '$enginePosix/packaging/functions.sh'
install_assemblies '$enginePosix' '$stagePosix/engine/openra/bin' 'win-x64' 'True' 'True' 'False'
install_data '$enginePosix' '$stagePosix/engine/openra' 'ra'
"@
& "C:\Program Files\Git\bin\bash.exe" -lc $packageCommand
if ($LASTEXITCODE -ne 0) {
    throw "OpenRA portable engine packaging failed."
}

$pyinstallerWork = Join-Path $artifactRoot "package\pyinstaller-work"
$pyinstallerSpec = Join-Path $artifactRoot "package\pyinstaller-spec"
& $python -m PyInstaller --noconfirm --clean --onefile `
    --name openra-ai-companion `
    --paths (Join-Path $repositoryRoot "services\companion\src") `
    --collect-all sounddevice `
    --distpath (Join-Path $stageRoot "bin") `
    --workpath $pyinstallerWork `
    --specpath $pyinstallerSpec `
    (Join-Path $repositoryRoot "apps\launcher\companion_entry.py")
if ($LASTEXITCODE -ne 0) {
    throw "Companion executable packaging failed."
}

$launcherTarget = Join-Path $stageRoot "apps\launcher"
$missionTarget = Join-Path $stageRoot "generated\missions"
New-Item -ItemType Directory -Path $launcherTarget -Force | Out-Null
New-Item -ItemType Directory -Path $missionTarget -Force | Out-Null
Copy-Item -LiteralPath (Join-Path $repositoryRoot "apps\launcher\Start-OpenRAAI.ps1") -Destination $launcherTarget
Copy-Item -LiteralPath (Join-Path $repositoryRoot "apps\launcher\Install-OpenRAContent.ps1") -Destination $launcherTarget
Copy-Item -LiteralPath (Join-Path $repositoryRoot "Play-OpenRAAI.cmd") -Destination $stageRoot
Copy-Item -LiteralPath (Join-Path $repositoryRoot "generated\missions\riyadh-crossing-42.oramap") -Destination $missionTarget
Copy-Item -LiteralPath (Join-Path $repositoryRoot ".env.example") -Destination $stageRoot
Copy-Item -LiteralPath (Join-Path $repositoryRoot "README.md") -Destination $stageRoot
Copy-Item -LiteralPath (Join-Path $repositoryRoot "LICENSE") -Destination $stageRoot

$manifest = [ordered]@{
    product = "OpenRA AI"
    version = $Version
    platform = "windows-x64"
    engine_commit = (git -C $engineRoot rev-parse HEAD).Trim()
    product_commit = (git -C $repositoryRoot rev-parse HEAD).Trim()
    entrypoint = "Play-OpenRAAI.cmd"
    bundled_map = "generated/missions/riyadh-crossing-42.oramap"
    content = "Downloaded on first run from OpenRA's supported Red Alert quick-install mirrors"
}
$manifest | ConvertTo-Json | Set-Content -LiteralPath (Join-Path $stageRoot "release.json") -Encoding UTF8

if (Test-Path -LiteralPath $releaseArchive) {
    Remove-Item -LiteralPath $releaseArchive
}
Add-Type -AssemblyName System.IO.Compression.FileSystem
[IO.Compression.ZipFile]::CreateFromDirectory($stageRoot, $releaseArchive, [IO.Compression.CompressionLevel]::Optimal, $true)
$hash = (Get-FileHash -LiteralPath $releaseArchive -Algorithm SHA256).Hash.ToLowerInvariant()
$hash | Set-Content -LiteralPath "$releaseArchive.sha256" -Encoding ASCII

[pscustomobject]@{
    Archive = $releaseArchive
    Bytes = (Get-Item -LiteralPath $releaseArchive).Length
    SHA256 = $hash
}
