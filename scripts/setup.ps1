[CmdletBinding()]
param([switch]$SkipEngine)

$ErrorActionPreference = "Stop"
$repositoryRoot = Split-Path -Parent $PSScriptRoot
$virtualEnvironment = Join-Path $repositoryRoot ".venv"
$python = Join-Path $virtualEnvironment "Scripts\python.exe"

if (-not (Test-Path -LiteralPath $python)) {
    python -m venv $virtualEnvironment
}

& $python -m pip install --disable-pip-version-check -e "$repositoryRoot\services\worldgen" -e "$repositoryRoot\services\companion[voice,package]"

Push-Location (Join-Path $repositoryRoot "apps\web")
try {
    npm install
}
finally {
    Pop-Location
}

if (-not $SkipEngine) {
    $userDotnet = Join-Path $env:USERPROFILE ".dotnet"
    if (Test-Path -LiteralPath (Join-Path $userDotnet "dotnet.exe")) {
        $env:PATH = "$userDotnet;$env:PATH"
    }
    $env:DOTNET_ROLL_FORWARD = "Major"
    Push-Location (Join-Path $repositoryRoot "engine\openra")
    try {
        dotnet build OpenRA.sln -c Release --nologo -p:TargetPlatform=win-x64
    }
    finally {
        Pop-Location
    }
}

Write-Host "OpenRA AI local environment is ready." -ForegroundColor Green
