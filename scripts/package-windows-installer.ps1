[CmdletBinding()]
param(
    [string]$Version = "0.1.0-alpha.1",
    [string]$StageRoot,
    [switch]$RequireSignatures
)

$ErrorActionPreference = "Stop"
$repositoryRoot = Split-Path -Parent $PSScriptRoot
$artifactRoot = Join-Path $repositoryRoot "artifacts"
$releaseRoot = Join-Path $artifactRoot "releases"
$releaseName = "OpenRA-AI-$Version-windows-x64"
$portableArchive = Join-Path $releaseRoot "$releaseName.zip"
$installer = Join-Path $releaseRoot "$releaseName-setup.exe"
$installerScript = Join-Path $repositoryRoot "apps\installer\windows\OpenRAAI.nsi"
$brandIcon = Join-Path $repositoryRoot "assets\brand\rtsai.ico"
$temporaryStage = $null
$signingScript = Join-Path $PSScriptRoot "sign-windows-artifacts.ps1"
$signaturesRequired = $RequireSignatures -or $env:OPENRA_AI_OFFICIAL_RELEASE -eq "1"

foreach ($required in @($portableArchive, $installerScript, $brandIcon)) {
    if (-not (Test-Path -LiteralPath $required)) {
        throw "Windows installer input is missing: $required"
    }
}

if ([string]::IsNullOrWhiteSpace($StageRoot)) {
    $StageRoot = Join-Path $artifactRoot "package\windows-x64\$releaseName"
}

if (-not (Test-Path -LiteralPath $StageRoot)) {
    $temporaryStage = Join-Path $artifactRoot "package\windows-installer\$releaseName"
    if (Test-Path -LiteralPath $temporaryStage) {
        $temporaryResolved = (Resolve-Path -LiteralPath $temporaryStage).Path
        $artifactResolved = (Resolve-Path -LiteralPath $artifactRoot).Path
        if (-not $temporaryResolved.StartsWith($artifactResolved + [IO.Path]::DirectorySeparatorChar)) {
            throw "Refusing to replace an installer stage outside artifacts."
        }
        Remove-Item -LiteralPath $temporaryResolved -Recurse
    }
    New-Item -ItemType Directory -Path $temporaryStage -Force | Out-Null
    Expand-Archive -LiteralPath $portableArchive -DestinationPath $temporaryStage
    $StageRoot = Join-Path $temporaryStage $releaseName
}

foreach ($required in @(
    (Join-Path $StageRoot "Play-OpenRAAI.cmd"),
    (Join-Path $StageRoot "bin\openra-ai-companion.exe"),
    (Join-Path $StageRoot "bin\openra-ai-runtime.exe"),
    (Join-Path $StageRoot "engine\openra\bin\OpenRA-AI.exe")
)) {
    if (-not (Test-Path -LiteralPath $required)) {
        throw "Windows installer payload is incomplete: $required"
    }
}

$shippedExecutables = @(
    (Join-Path $StageRoot "bin\openra-ai-companion.exe"),
    (Join-Path $StageRoot "bin\openra-ai-runtime.exe"),
    (Join-Path $StageRoot "engine\openra\bin\OpenRA-AI.exe"),
    (Join-Path $StageRoot "engine\openra\bin\OpenRA.exe"),
    (Join-Path $StageRoot "engine\openra\bin\OpenRA.Server.exe"),
    (Join-Path $StageRoot "engine\openra\bin\OpenRA.Utility.exe")
)
if ($signaturesRequired) {
    & $signingScript -Paths $shippedExecutables -RequireSignatures -VerifyOnly
}

$payloadBrand = Join-Path $StageRoot "assets\brand"
New-Item -ItemType Directory -Path $payloadBrand -Force | Out-Null
Copy-Item -LiteralPath $brandIcon -Destination (Join-Path $payloadBrand "rtsai.ico") -Force

$aiPack = Join-Path $releaseRoot "OpenRA-AI-AI-Pack-$Version-windows-x64.zip"
$aiPackChecksum = "$aiPack.sha256"
foreach ($required in @($aiPack, $aiPackChecksum)) {
    if (-not (Test-Path -LiteralPath $required)) {
        throw "Build the Windows AI pack before the installer: $required"
    }
}
$aiPackHash = (Get-Content -LiteralPath $aiPackChecksum -Raw).Split(" ")[0].Trim().ToLowerInvariant()
$aiPackUrl = "https://github.com/alibad/OpenRA-AI/releases/download/v$Version/$([IO.Path]::GetFileName($aiPack))"

$makensisCommand = Get-Command "makensis.exe" -ErrorAction SilentlyContinue
$makensisPath = if ($makensisCommand) { $makensisCommand.Source } else { $null }
if (-not $makensisPath) {
    $candidates = @(
        (Join-Path $env:LOCALAPPDATA "Programs\NSIS\makensis.exe"),
        "C:\Program Files (x86)\NSIS\makensis.exe",
        "C:\Program Files\NSIS\makensis.exe"
    )
    $makensisPath = $candidates | Where-Object { Test-Path -LiteralPath $_ } | Select-Object -First 1
}
if (-not $makensisPath) {
    throw "NSIS 3 is required. Install it locally with: winget install --id NSIS.NSIS --exact"
}

New-Item -ItemType Directory -Path $releaseRoot -Force | Out-Null
if (Test-Path -LiteralPath $installer) {
    Remove-Item -LiteralPath $installer
}

$makensisArguments = @(
    "/V2",
    "/DVERSION=$Version",
    "/DPAYLOAD=$StageRoot",
    "/DOUTFILE=$installer",
    "/DICON=$brandIcon",
    "/DAIPACKURL=$aiPackUrl",
    "/DAIPACKSHA256=$aiPackHash"
)
if ($signaturesRequired) {
    # NSIS 3.08+ invokes this for the generated uninstaller before embedding it.
    # The helper resolves the certificate from the Windows certificate store;
    # no key material or password is passed through the compiler command line.
    $makensisArguments += "/DUNINSTALLSIGNER=$signingScript"
}
$makensisArguments += $installerScript

& $makensisPath @makensisArguments
if ($LASTEXITCODE -ne 0 -or -not (Test-Path -LiteralPath $installer)) {
    throw "NSIS did not produce the Windows setup executable."
}

& $signingScript -Paths @($installer) -RequireSignatures:$signaturesRequired

$hash = (Get-FileHash -LiteralPath $installer -Algorithm SHA256).Hash.ToLowerInvariant()
$hash | Set-Content -LiteralPath "$installer.sha256" -Encoding ASCII

[pscustomobject]@{
    Installer = $installer
    Bytes = (Get-Item -LiteralPath $installer).Length
    SHA256 = $hash
}
