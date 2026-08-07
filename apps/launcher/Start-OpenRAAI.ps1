[CmdletBinding()]
param(
    [string]$Map,
    [switch]$NoSpeech,
    [int]$BridgePort = 9998
)

$ErrorActionPreference = "Stop"
$repositoryRoot = Split-Path -Parent (Split-Path -Parent $PSScriptRoot)
$engineRoot = Join-Path $repositoryRoot "engine\openra"
$python = Join-Path $repositoryRoot ".venv\Scripts\python.exe"
$companion = Join-Path $repositoryRoot ".venv\Scripts\openra-ai-companion.exe"
$game = Join-Path $engineRoot "bin\OpenRA.exe"

foreach ($required in @($python, $companion, $game)) {
    if (-not (Test-Path -LiteralPath $required)) {
        throw "Missing local build output: $required. Run scripts\setup.ps1 first."
    }
}

$supportRoot = Join-Path $env:APPDATA "OpenRA"
$mapArgument = $null
if ($Map) {
    $mapSource = (Resolve-Path -LiteralPath $Map).Path
    if ([IO.Path]::GetExtension($mapSource) -ne ".oramap") {
        throw "The selected map must be an .oramap package."
    }

    $version = (Get-Content -LiteralPath (Join-Path $engineRoot "VERSION") -Raw).Trim()
    $mapDirectory = Join-Path $supportRoot "maps\ra\$version"
    New-Item -ItemType Directory -Path $mapDirectory -Force | Out-Null
    $installedMap = Join-Path $mapDirectory ([IO.Path]::GetFileName($mapSource))
    Copy-Item -LiteralPath $mapSource -Destination $installedMap -Force
    $mapArgument = "Launch.Map=$([IO.Path]::GetFileName($installedMap))"
}

$logDirectory = Join-Path $repositoryRoot "artifacts\companion"
New-Item -ItemType Directory -Path $logDirectory -Force | Out-Null
$watchArguments = @("-m", "openra_ai_companion.cli", "watch", "--bridge", "127.0.0.1:$BridgePort")
if (-not $NoSpeech) {
    $watchArguments += "--speak"
}

$watcher = Start-Process -FilePath $python -ArgumentList $watchArguments `
    -WorkingDirectory $repositoryRoot -WindowStyle Hidden -PassThru `
    -RedirectStandardOutput (Join-Path $logDirectory "watch.out.log") `
    -RedirectStandardError (Join-Path $logDirectory "watch.err.log")

$env:DOTNET_ROLL_FORWARD = "Major"
$env:OPENRA_AI_COMPANION = "1"
$env:OPENRA_AI_GRPC_PORT = "$BridgePort"
$arguments = @("Engine.EngineDir=$engineRoot", "Game.Mod=ra")
if ($mapArgument) {
    $arguments += $mapArgument
}

try {
    & $game @arguments
}
finally {
    if (-not $watcher.HasExited) {
        Stop-Process -Id $watcher.Id
    }
}
