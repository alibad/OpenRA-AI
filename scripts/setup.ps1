[CmdletBinding()]
param([switch]$SkipEngine)

$ErrorActionPreference = "Stop"
$repositoryRoot = Split-Path -Parent $PSScriptRoot
$virtualEnvironment = Join-Path $repositoryRoot ".venv"
$python = Join-Path $virtualEnvironment "Scripts\python.exe"

if (-not (Test-Path -LiteralPath $python)) {
    python -m venv $virtualEnvironment
}

& $python -m pip install --disable-pip-version-check -e "$repositoryRoot\services\worldgen" -e "$repositoryRoot\services\companion[voice,package,local-runtime]"

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
    $dotnetVersion = (& dotnet --version).Trim()
    if ($LASTEXITCODE -ne 0 -or $dotnetVersion -notmatch '^(\d+)\.' -or [int]$Matches[1] -lt 10) {
        throw "OpenRA main requires the .NET 10 SDK or newer. Install .NET 10 and rerun setup."
    }
    Push-Location (Join-Path $repositoryRoot "engine\openra")
    try {
        dotnet build OpenRA.slnx -c Release --nologo -p:TargetPlatform=win-x64
    }
    finally {
        Pop-Location
    }

    & (Join-Path $PSScriptRoot "build-windows-launcher.ps1")
}

Write-Host "OpenRA AI local environment is ready." -ForegroundColor Green
