[CmdletBinding()]
param([switch]$SkipEngine, [switch]$SkipWeb)

$ErrorActionPreference = "Stop"
$repositoryRoot = Split-Path -Parent $PSScriptRoot
$virtualEnvironment = Join-Path $repositoryRoot ".venv"
$python = Join-Path $virtualEnvironment "Scripts\python.exe"
$canonical = Join-Path (Split-Path -Parent $repositoryRoot) "OpenRA"
$engineRoot = if (Test-Path (Join-Path $canonical "OpenRA.slnx")) { $canonical } else { Join-Path $repositoryRoot "engine\openra" }

if (-not (Test-Path -LiteralPath $python)) {
    python -m venv $virtualEnvironment
}

& $python -m ensurepip --upgrade
& $python -m pip install --disable-pip-version-check -e "$repositoryRoot\services\worldgen" -e "$repositoryRoot\services\companion[voice,package,local-runtime]"
if ($LASTEXITCODE -ne 0) { throw "Companion dependency installation failed." }
$env:PYTHONUTF8 = "1"
& $python (Join-Path $PSScriptRoot "setup-local-ai.py")
if ($LASTEXITCODE -ne 0) { throw "Local AI setup failed." }

if (-not $SkipWeb) {
Push-Location (Join-Path $repositoryRoot "apps\web")
try {
    npm install
}
finally {
    Pop-Location
}
}

if (-not $SkipEngine) {
    $env:DOTNET_ROLL_FORWARD = "Major"
    $dotnetVersion = (& dotnet --version).Trim()
    if ($LASTEXITCODE -ne 0 -or $dotnetVersion -notmatch '^(\d+)\.' -or [int]$Matches[1] -lt 10) {
        throw "OpenRA main requires the .NET 10 SDK or newer. Install .NET 10 and rerun setup."
    }
    Push-Location $engineRoot
    try {
        dotnet build OpenRA.slnx -c Release --nologo -p:TargetPlatform=win-x64
        if ($LASTEXITCODE -ne 0) { throw "Engine build failed." }
    }
    finally {
        Pop-Location
    }

    & (Join-Path $PSScriptRoot "build-windows-launcher.ps1") -EngineRoot $engineRoot
    $env:PYTHONUTF8 = "1"
    & $python (Join-Path $PSScriptRoot "prepare-local-ra2.py") --engine $engineRoot
    if ($LASTEXITCODE -ne 0) { throw "RA2 preparation failed." }
}

Write-Host "OpenRA AI local environment is ready." -ForegroundColor Green
