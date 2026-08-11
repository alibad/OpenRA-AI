[CmdletBinding()]
param(
    [switch]$Regenerate,
    [switch]$Headless
)

$ErrorActionPreference = "Stop"
$repositoryRoot = Split-Path -Parent $PSScriptRoot
$python = Join-Path $repositoryRoot ".venv\Scripts\python.exe"
$engineRoot = Join-Path $repositoryRoot "engine\openra"
$missionDirectory = Join-Path $repositoryRoot "generated\missions"
$mission = Join-Path $missionDirectory "jizan-corridor-20260811.oramap"
$launcher = Join-Path $repositoryRoot "apps\launcher\Start-OpenRAAI.ps1"

foreach ($required in @($python, $launcher, (Join-Path $engineRoot "bin\OpenRA.exe"))) {
    if (-not (Test-Path -LiteralPath $required)) {
        throw "Missing required build file: $required. Run scripts\setup.ps1 first."
    }
}

if ($Regenerate -or -not (Test-Path -LiteralPath $mission)) {
    New-Item -ItemType Directory -Path $missionDirectory -Force | Out-Null
    $env:DOTNET_ROLL_FORWARD = "Major"
    $env:OPENRA_AI_ENGINE_DIR = $engineRoot
    Push-Location $repositoryRoot
    try {
        & $python -m openra_ai_worldgen.cli generate `
            --lat 16.8892 `
            --lon 42.5511 `
            --title "Jizan Corridor" `
            --location "Jizan, Saudi Arabia" `
            --radius 2000 `
            --size 96 `
            --seed 20260811 `
            --scenario jizan-corridor-2026 `
            --player-faction saudi `
            --opponent-faction yemen `
            --archetype convoy-defense `
            --mode playability-first `
            --imagery auto `
            --output $missionDirectory
        if ($LASTEXITCODE -ne 0) {
            throw "Jizan Corridor generation failed with exit code $LASTEXITCODE."
        }
    }
    finally {
        Pop-Location
    }
}

$launchArguments = @{ Map = $mission }
if ($Headless) {
    $launchArguments.Headless = $true
}

& $launcher @launchArguments
