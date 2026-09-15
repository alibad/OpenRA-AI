[CmdletBinding()]
param(
    [string]$Map,
    [switch]$NoSpeech,
    [switch]$NoVoiceHotkeys,
    [switch]$SkipContentInstall,
    [switch]$Headless,
    [ValidateSet("classic", "ra2")]
    [string]$Game,
    [ValidateSet("beginner", "easy", "medium", "rush", "normal", "turtle", "naval")]
    [string]$OpponentBot = "normal",
    [int]$BridgePort = 9998,
    [int]$AIConsolePort = 8787,
    [int]$WorldStudioPort = 8788,
    [string]$EncodedGameArguments
)

$ErrorActionPreference = "Stop"
$repositoryRoot = Split-Path -Parent (Split-Path -Parent $PSScriptRoot)
# Development uses the canonical sibling; portable installations use their bundled engine.
$canonical = Join-Path (Split-Path -Parent $repositoryRoot) "OpenRA"
$engineRoot = if (Test-Path (Join-Path $canonical "launch-game.ps1")) {
    $canonical
} else { Join-Path $repositoryRoot "engine\openra" }
$launcher = Join-Path $engineRoot "launch-game.ps1"
if (-not (Test-Path -LiteralPath $launcher)) { throw "Missing engine launcher. Run scripts\setup.ps1." }

$gameArguments = @()
if ($EncodedGameArguments) {
    $gameArguments = @([Text.Encoding]::UTF8.GetString([Convert]::FromBase64String($EncodedGameArguments)) | ConvertFrom-Json)
    if ($gameArguments | Where-Object { $_ -isnot [string] }) { throw "Every game argument must be a string." }
}
$supportRoot = if (Test-Path (Join-Path $engineRoot "Support")) {
    Join-Path $engineRoot "Support"
} else { Join-Path $env:APPDATA "OpenRA" }
if (-not $SkipContentInstall) {
    & (Join-Path $PSScriptRoot "Install-OpenRAContent.ps1") -SupportRoot $supportRoot
}
if ($Map) {
    if ($Game -eq "ra2") { throw "The generated map launcher currently targets the classic OpenRA ruleset. Start without -Map to choose Red Alert 2 from the main menu." }
    $source = (Resolve-Path -LiteralPath $Map).Path
    if ([IO.Path]::GetExtension($source) -ne ".oramap") { throw "Select an .oramap map." }
    $version = (Get-Content (Join-Path $engineRoot "VERSION") -Raw).Trim()
    $directory = Join-Path $supportRoot "maps\ra\$version"
    New-Item -ItemType Directory -Path $directory -Force | Out-Null
    $destination = Join-Path $directory ([IO.Path]::GetFileName($source))
    if (Test-Path $destination) {
        if ((Get-FileHash $source).Hash -ne (Get-FileHash $destination).Hash) { throw "A different map already exists: $destination" }
    } else { Copy-Item -LiteralPath $source -Destination $destination }
    $gameArguments += @("Game.Mod=ra", "Launch.Map=$([IO.Path]::GetFileName($destination))", "Launch.Bots=Multi1:$OpponentBot")
}
if ($Game -and -not $Map) {
    $gameArguments += "Game.Mod=$(if ($Game -eq 'ra2') { 'ra2' } else { 'ra' })"
}
if ($Headless) { $gameArguments += "Game.Platform=Null" }
& $launcher -CompanionRoot $repositoryRoot -NoSpeech:$NoSpeech -NoVoiceHotkeys:$NoVoiceHotkeys -BridgePort $BridgePort -AIConsolePort $AIConsolePort -WorldStudioPort $WorldStudioPort -GameArguments $gameArguments
exit $LASTEXITCODE
