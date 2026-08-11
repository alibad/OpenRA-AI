[CmdletBinding()]
param(
    [string]$Map,
    [switch]$NoSpeech,
    [switch]$NoVoiceHotkeys,
    [switch]$SkipContentInstall,
    [switch]$Headless,
    [ValidateSet("beginner", "easy", "medium", "rush", "normal", "turtle", "naval")]
    [string]$OpponentBot = "normal",
    [int]$BridgePort = 9998,
    [int]$AIConsolePort = 8787,
    [int]$WorldStudioPort = 8788
)

$ErrorActionPreference = "Stop"
$repositoryRoot = Split-Path -Parent (Split-Path -Parent $PSScriptRoot)
$engineRoot = Join-Path $repositoryRoot "engine\openra"
$python = Join-Path $repositoryRoot ".venv\Scripts\python.exe"
$companion = Join-Path $repositoryRoot ".venv\Scripts\openra-ai-companion.exe"
$bundledCompanion = Join-Path $repositoryRoot "bin\openra-ai-companion.exe"
$game = Join-Path $engineRoot "bin\OpenRA.exe"
$contentInstaller = Join-Path $PSScriptRoot "Install-OpenRAContent.ps1"

foreach ($required in @($game, $contentInstaller)) {
    if (-not (Test-Path -LiteralPath $required)) {
        throw "Missing local build output: $required. Run scripts\setup.ps1 first."
    }
}

if (-not (Test-Path -LiteralPath $bundledCompanion)) {
    foreach ($required in @($python, $companion)) {
        if (-not (Test-Path -LiteralPath $required)) {
            throw "Missing local companion output: $required. Run scripts\setup.ps1 first."
        }
    }
}

$supportRoot = Join-Path $env:APPDATA "OpenRA"
$requiredContent = Join-Path $supportRoot "Content\ra\v2\allies.mix"
if ($SkipContentInstall) {
    if (-not (Test-Path -LiteralPath $requiredContent)) {
        throw "OpenRA Red Alert content is missing. Run apps\launcher\Install-OpenRAContent.ps1 first."
    }
}
else {
    & $contentInstaller
}

$version = (Get-Content -LiteralPath (Join-Path $engineRoot "VERSION") -Raw).Trim()
$mapDirectory = Join-Path $supportRoot "maps\ra\$version"
$missionOutput = Join-Path $repositoryRoot "generated\missions"
New-Item -ItemType Directory -Path $mapDirectory -Force | Out-Null
New-Item -ItemType Directory -Path $missionOutput -Force | Out-Null

$mapArgument = $null
if ($Map) {
    $mapSource = (Resolve-Path -LiteralPath $Map).Path
    if ([IO.Path]::GetExtension($mapSource) -ne ".oramap") {
        throw "The selected map must be an .oramap package."
    }

    $installedMap = Join-Path $mapDirectory ([IO.Path]::GetFileName($mapSource))
    Copy-Item -LiteralPath $mapSource -Destination $installedMap -Force
    $mapArgument = "Launch.Map=$([IO.Path]::GetFileName($installedMap))"
}

$logDirectory = Join-Path $repositoryRoot "artifacts\companion"
New-Item -ItemType Directory -Path $logDirectory -Force | Out-Null
$env:DOTNET_ROLL_FORWARD = "Major"
$env:OPENRA_AI_COMPANION = "1"
$env:OPENRA_AI_GRPC_PORT = "$BridgePort"
$env:OPENRA_AI_CONSOLE_URL = "http://127.0.0.1:$AIConsolePort/"
$env:OPENRA_AI_WORLD_STUDIO_URL = "http://127.0.0.1:$WorldStudioPort/"
$env:OPENRA_AI_ENGINE_DIR = $engineRoot
# OpenRA currently exposes its UI through the English Fluent bundle. The
# transcription setting follows this app language unless explicitly overridden.
if ([string]::IsNullOrWhiteSpace($env:OPENRA_AI_APP_LANGUAGE)) {
    $env:OPENRA_AI_APP_LANGUAGE = "en"
}
$arguments = @("Engine.EngineDir=$engineRoot", "Game.Mod=ra", "Launch.Bots=Multi1:$OpponentBot")
if ($Headless) {
    $arguments += "Game.Platform=Null"
}
else {
    # Always force the interactive renderer. Headless smoke tests persist their
    # platform choice in settings.yaml, which must not affect the next real game.
    $arguments += "Game.Platform=Default"
}
if ($mapArgument) {
    $arguments += $mapArgument
}

if (-not $NoSpeech -and -not $NoVoiceHotkeys) {
    Write-Host "AI controls: hold Ctrl+Space to ask, Ctrl+Enter accepts, Ctrl+Backspace rejects, Ctrl+Shift+A toggles AUTO, and Ctrl+Shift+M toggles voice. Remap them in Settings > Hotkeys > AI Assistant." -ForegroundColor Cyan
}

$gameStart = @{
    FilePath = $game
    ArgumentList = $arguments
    WorkingDirectory = $engineRoot
    PassThru = $true
}
if ($Headless) {
    $gameStart["WindowStyle"] = "Hidden"
    $gameStart["RedirectStandardOutput"] = Join-Path $logDirectory "game.out.log"
    $gameStart["RedirectStandardError"] = Join-Path $logDirectory "game.err.log"
}

$gameProcess = Start-Process @gameStart
$watchProgram = $python
$watchArguments = @("-u", "-m", "openra_ai_companion.cli", "watch")
if (Test-Path -LiteralPath $bundledCompanion) {
    $watchProgram = $bundledCompanion
    $watchArguments = @("watch")
}
$watchArguments += @("--bridge", "127.0.0.1:$BridgePort", "--game-pid", "$($gameProcess.Id)")
$watchArguments += @(
    "--control-port", "$AIConsolePort",
    "--worldgen-port", "$WorldStudioPort",
    "--mission-output", "`"$missionOutput`"",
    "--mission-install", "`"$mapDirectory`""
)
if (-not $NoSpeech) {
    $watchArguments += "--speak"
    if (-not $NoVoiceHotkeys) {
        $watchArguments += "--voice-hotkeys"
    }
}
else {
    $watchArguments += "--no-speak"
}

$env:PYTHONUNBUFFERED = "1"
$env:PYTHONUTF8 = "1"
$env:PYTHONIOENCODING = "utf-8"
$watcher = $null
try {
    $watcher = Start-Process -FilePath $watchProgram -ArgumentList $watchArguments `
        -WorkingDirectory $repositoryRoot -WindowStyle Hidden -PassThru `
        -RedirectStandardOutput (Join-Path $logDirectory "watch.out.log") `
        -RedirectStandardError (Join-Path $logDirectory "watch.err.log")
    $gameProcess.WaitForExit()
    if ($gameProcess.ExitCode -ne 0) {
        throw "OpenRA exited with code $($gameProcess.ExitCode)."
    }
}
finally {
    if ($watcher -and -not $watcher.HasExited) {
        if (-not $watcher.WaitForExit(2500)) {
            Stop-Process -Id $watcher.Id
        }
    }
    if (-not $gameProcess.HasExited) {
        Stop-Process -Id $gameProcess.Id -Force -ErrorAction SilentlyContinue
    }
}
