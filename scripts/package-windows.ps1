[CmdletBinding()]
param(
    [string]$Version = "0.1.0-alpha.1",
    [switch]$SkipInstaller,
    [switch]$RequireSignatures
)

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
$brandIcon = Join-Path $repositoryRoot "assets\brand\rtsai.ico"
$aiPackLock = Join-Path $repositoryRoot "packaging\ai-pack.lock.json"
$aiRuntimeLock = Join-Path $repositoryRoot "packaging\ai-runtime.lock.json"
$modelNotices = Join-Path $repositoryRoot "packaging\THIRD_PARTY_MODELS.md"
$sampleMission = Join-Path $repositoryRoot "generated\missions\riyadh-crossing-42.oramap"
$signingScript = Join-Path $PSScriptRoot "sign-windows-artifacts.ps1"
$signaturesRequired = $RequireSignatures -or $env:OPENRA_AI_OFFICIAL_RELEASE -eq "1"

foreach ($required in @($python, $brandIcon, $aiPackLock, $aiRuntimeLock, $modelNotices)) {
    if (-not (Test-Path -LiteralPath $required)) {
        throw "Packaging input is missing: $required"
    }
}

& $python -m openra_ai_companion.cli voice-check --dependencies-only
if ($LASTEXITCODE -ne 0) {
    throw "Windows packaging requires the companion voice extra. Run scripts\setup.ps1 again."
}

if (-not (Test-Path -LiteralPath $sampleMission)) {
    & $python -m openra_ai_worldgen.cli generate --lat 24.7136 --lon 46.6753 `
        --title "Riyadh Crossing" --location "Riyadh, Saudi Arabia" `
        --imagery terrain --mode playability-first --seed 42 --offline
    if ($LASTEXITCODE -ne 0 -or -not (Test-Path -LiteralPath $sampleMission)) {
        throw "Sample mission generation failed."
    }
}
& $python -m openra_ai_worldgen.cli validate $sampleMission
if ($LASTEXITCODE -ne 0) {
    throw "Sample mission validation failed."
}

$runningEngine = @(Get-Process -Name "OpenRA", "OpenRA-AI" -ErrorAction SilentlyContinue | Where-Object {
    $_.Path -and $_.Path.StartsWith($engineRoot + [IO.Path]::DirectorySeparatorChar, [StringComparison]::OrdinalIgnoreCase)
})
if ($runningEngine.Count -gt 0) {
    $processIds = ($runningEngine.Id | Sort-Object) -join ", "
    throw "Close OpenRA processes running from this checkout before packaging (PID: $processIds)."
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

& (Join-Path $PSScriptRoot "build-windows-launcher.ps1") `
    -OutputDirectory (Join-Path $stageRoot "engine\openra\bin") `
    -SelfContained

$pyinstallerWork = Join-Path $artifactRoot "package\pyinstaller-work"
$pyinstallerSpec = Join-Path $artifactRoot "package\pyinstaller-spec"
& $python -m PyInstaller --noconfirm --clean --onefile `
    --name openra-ai-companion `
    --icon $brandIcon `
    --paths (Join-Path $repositoryRoot "services\companion\src") `
    --collect-all sounddevice `
    --collect-data agents `
    --distpath (Join-Path $stageRoot "bin") `
    --workpath $pyinstallerWork `
    --specpath $pyinstallerSpec `
    (Join-Path $repositoryRoot "apps\launcher\companion_entry.py")
if ($LASTEXITCODE -ne 0) {
    throw "Companion executable packaging failed."
}
$companionExecutable = Join-Path $stageRoot "bin\openra-ai-companion.exe"
& $companionExecutable voice-check --dependencies-only
if ($LASTEXITCODE -ne 0) {
    throw "Packaged companion is missing local microphone capture support."
}

& $python -m PyInstaller --noconfirm --clean --onefile `
    --name openra-ai-runtime `
    --icon $brandIcon `
    --paths (Join-Path $repositoryRoot "services\companion\src") `
    --collect-all kokoro_onnx `
    --collect-all espeakng_loader `
    --collect-all phonemizer `
    --collect-all language_tags `
    --distpath (Join-Path $stageRoot "bin") `
    --workpath (Join-Path $pyinstallerWork "local-runtime") `
    --specpath (Join-Path $pyinstallerSpec "local-runtime") `
    (Join-Path $repositoryRoot "apps\launcher\local_ai_entry.py")
if ($LASTEXITCODE -ne 0) {
    throw "Local AI runtime executable packaging failed."
}

$launcherTarget = Join-Path $stageRoot "apps\launcher"
$missionTarget = Join-Path $stageRoot "generated\missions"
New-Item -ItemType Directory -Path $launcherTarget -Force | Out-Null
New-Item -ItemType Directory -Path $missionTarget -Force | Out-Null
Copy-Item -LiteralPath (Join-Path $repositoryRoot "apps\launcher\Start-OpenRAAI.ps1") -Destination $launcherTarget
Copy-Item -LiteralPath (Join-Path $repositoryRoot "apps\launcher\Install-OpenRAContent.ps1") -Destination $launcherTarget
Copy-Item -LiteralPath (Join-Path $repositoryRoot "apps\launcher\Install-AIPack.ps1") -Destination $launcherTarget
Copy-Item -LiteralPath (Join-Path $repositoryRoot "Play-OpenRAAI.cmd") -Destination $stageRoot
Copy-Item -LiteralPath $sampleMission -Destination $missionTarget
Copy-Item -LiteralPath (Join-Path $repositoryRoot ".env.example") -Destination $stageRoot
Copy-Item -LiteralPath (Join-Path $repositoryRoot "README.md") -Destination $stageRoot
Copy-Item -LiteralPath (Join-Path $repositoryRoot "LICENSE") -Destination $stageRoot
$packagingMetadata = Join-Path $stageRoot "packaging"
New-Item -ItemType Directory -Path $packagingMetadata -Force | Out-Null
Copy-Item -LiteralPath $aiPackLock -Destination $packagingMetadata
Copy-Item -LiteralPath $aiRuntimeLock -Destination $packagingMetadata
Copy-Item -LiteralPath $modelNotices -Destination $packagingMetadata
$brandTarget = Join-Path $stageRoot "assets\brand"
New-Item -ItemType Directory -Path $brandTarget -Force | Out-Null
Copy-Item -LiteralPath $brandIcon -Destination (Join-Path $brandTarget "rtsai.ico")

$shippedExecutables = @(
    (Join-Path $stageRoot "bin\openra-ai-companion.exe"),
    (Join-Path $stageRoot "bin\openra-ai-runtime.exe"),
    (Join-Path $stageRoot "engine\openra\bin\OpenRA-AI.exe"),
    (Join-Path $stageRoot "engine\openra\bin\OpenRA.exe"),
    (Join-Path $stageRoot "engine\openra\bin\OpenRA.Server.exe"),
    (Join-Path $stageRoot "engine\openra\bin\OpenRA.Utility.exe")
)
& $signingScript -Paths $shippedExecutables -RequireSignatures:$signaturesRequired

$manifest = [ordered]@{
    product = "OpenRA AI"
    version = $Version
    platform = "windows-x64"
    engine_commit = (git -C $engineRoot rev-parse HEAD).Trim()
    product_commit = (git -C $repositoryRoot rev-parse HEAD).Trim()
    entrypoint = "Play-OpenRAAI.cmd"
    bundled_map = "generated/missions/riyadh-crossing-42.oramap"
    content = "Downloaded on first run from OpenRA's supported Red Alert quick-install mirrors"
    ai_pack = [ordered]@{
        manifest = "packaging/ai-pack.lock.json"
        runtime_manifest = "packaging/ai-runtime.lock.json"
        installer_default = $true
        portable_install = "Extract the matching AI pack into the ai folder, or configure an external provider."
        runtime_cost = "No hosted-provider charge"
    }
}
$manifest | ConvertTo-Json | Set-Content -LiteralPath (Join-Path $stageRoot "release.json") -Encoding UTF8

if (Test-Path -LiteralPath $releaseArchive) {
    Remove-Item -LiteralPath $releaseArchive
}
Add-Type -AssemblyName System.IO.Compression.FileSystem
[IO.Compression.ZipFile]::CreateFromDirectory($stageRoot, $releaseArchive, [IO.Compression.CompressionLevel]::Optimal, $true)
$hash = (Get-FileHash -LiteralPath $releaseArchive -Algorithm SHA256).Hash.ToLowerInvariant()
$hash | Set-Content -LiteralPath "$releaseArchive.sha256" -Encoding ASCII

$installerResult = $null
if (-not $SkipInstaller) {
    $installerResult = & (Join-Path $PSScriptRoot "package-windows-installer.ps1") `
        -Version $Version -StageRoot $stageRoot -RequireSignatures:$signaturesRequired
}

[pscustomobject]@{
    Archive = $releaseArchive
    Bytes = (Get-Item -LiteralPath $releaseArchive).Length
    SHA256 = $hash
    Installer = $installerResult.Installer
    InstallerBytes = $installerResult.Bytes
    InstallerSHA256 = $installerResult.SHA256
}
