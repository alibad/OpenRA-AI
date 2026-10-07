<#
.SYNOPSIS
Freeze the companion and its loopback AI gateway into the folder the RTS AI mod ships as `companion\`.

.DESCRIPTION
One PyInstaller --onedir bundle (`rtsai-companion.exe`) hosts every sidecar role:

    rtsai-companion.exe watch ...          the co-commander (started by OpenRA.Mods.RTSAI's CompanionHost)
    rtsai-companion.exe runtime serve ...  the loopback gateway (hosted / local / external), started by the companion
    rtsai-companion.exe pack install ...   checksum-verified AI pack install (run by the installer)
    rtsai-companion.exe game-mcp           the MCP tool server used by the interactive planner

--onedir instead of --onefile: nothing is unpacked to %TEMP% on every launch, startup is
faster, and a killed process leaves no _MEI folder behind.

The bundle also carries the pinned llama.cpp / whisper.cpp CPU runtimes (ai\runtime, from
packaging\ai-runtime.lock.json, SHA-256 verified) and the AI pack lock. The models
themselves are never bundled: the installer or the game downloads the voice pack.

.EXAMPLE
./scripts/package-rtsai-companion.ps1 -OutputDirectory C:\temp\rtsai-payload
# -> C:\temp\rtsai-payload\companion\rtsai-companion.exe
#
# Optional: -VoicePackOutput C:\temp\release\RTSAI-VoicePack-0.2.0-alpha.1.zip builds the offline voice pack.
#>
[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)]
    [string]$OutputDirectory,
    [string]$Python,
    [string]$WorkDirectory,
    [string]$CacheDirectory,
    [string]$VoicePackOutput,
    [string]$ModelSourceDirectory
)

$ErrorActionPreference = "Stop"

function Invoke-Native {
    # Windows PowerShell 5.1 turns a native tool's stderr into terminating errors when the
    # caller redirects output; run tools with Continue and judge them by their exit code.
    param([Parameter(Mandatory = $true)][string]$FilePath, [string[]]$Arguments = @(), [string]$Failure)
    $previous = $ErrorActionPreference
    $ErrorActionPreference = "Continue"
    try {
        & $FilePath @Arguments 2>&1 | ForEach-Object { "$_" } | Out-Host
        $code = $LASTEXITCODE
    } finally {
        $ErrorActionPreference = $previous
    }
    if ($code -ne 0) { throw "$Failure (exit $code)" }
}
$repositoryRoot = Split-Path -Parent $PSScriptRoot
if (-not $Python) { $Python = Join-Path $repositoryRoot ".venv\Scripts\python.exe" }
if (-not (Test-Path -LiteralPath $Python)) {
    throw "Python with the companion dependencies and PyInstaller is required (run scripts\setup.ps1, or pass -Python)."
}
$OutputDirectory = [IO.Path]::GetFullPath($OutputDirectory)
if (-not $WorkDirectory) { $WorkDirectory = Join-Path $repositoryRoot "artifacts\package\rtsai-companion" }
if (-not $CacheDirectory) { $CacheDirectory = Join-Path $repositoryRoot "artifacts\download-cache\ai-pack" }
$WorkDirectory = [IO.Path]::GetFullPath($WorkDirectory)
$brandIcon = Join-Path $repositoryRoot "assets\brand\rtsai.ico"
$entry = Join-Path $repositoryRoot "apps\launcher\companion_entry.py"
$sources = @((Join-Path $repositoryRoot "services\companion\src"), (Join-Path $repositoryRoot "services\worldgen\src"))
$companionRoot = Join-Path $OutputDirectory "companion"

foreach ($required in @($brandIcon, $entry) + $sources) {
    if (-not (Test-Path -LiteralPath $required)) { throw "Packaging input is missing: $required" }
}
if (Test-Path -LiteralPath $companionRoot) {
    throw "Refusing to overwrite an existing companion folder: $companionRoot"
}

# Freeze from this checkout's sources, even when the venv has an editable install of another checkout.
$env:PYTHONPATH = ($sources -join [IO.Path]::PathSeparator)
$env:PYTHONUTF8 = "1"
Invoke-Native $Python @("-c", "import openra_ai_companion, sys; sys.exit(0 if openra_ai_companion.__file__.startswith(sys.argv[1]) else 3)", $sources[0]) "The companion package does not resolve to $($sources[0])."

$dist = Join-Path $WorkDirectory "dist"
New-Item -ItemType Directory -Path $WorkDirectory -Force | Out-Null
$pyinstallerArguments = @(
    "-m", "PyInstaller", "--noconfirm", "--clean", "--onedir",
    "--name", "rtsai-companion",
    "--icon", $brandIcon,
    "--distpath", $dist,
    "--workpath", (Join-Path $WorkDirectory "build"),
    "--specpath", (Join-Path $WorkDirectory "spec"),
    "--collect-all", "sounddevice",
    "--collect-data", "agents",
    "--collect-data", "openra_ai_companion",
    "--collect-all", "kokoro_onnx",
    "--collect-all", "espeakng_loader",
    "--collect-all", "phonemizer",
    "--collect-all", "language_tags",
    "--hidden-import", "openra_ai_companion.local_runtime",
    "--hidden-import", "openra_ai_companion.pack_cli",
    "--hidden-import", "openra_ai_companion.game_mcp",
    "--exclude-module", "pytest",
    "--exclude-module", "_pytest",
    "--exclude-module", "grpc_tools"
)
foreach ($source in $sources) { $pyinstallerArguments += @("--paths", $source) }
$pyinstallerArguments += $entry
Invoke-Native $Python $pyinstallerArguments "PyInstaller failed to freeze the companion."

$frozen = Join-Path $dist "rtsai-companion"
$executable = Join-Path $frozen "rtsai-companion.exe"
New-Item -ItemType Directory -Path $OutputDirectory -Force | Out-Null
Copy-Item -LiteralPath $frozen -Destination $companionRoot -Recurse
$executable = Join-Path $companionRoot "rtsai-companion.exe"

$packagingTarget = Join-Path $companionRoot "packaging"
New-Item -ItemType Directory -Path $packagingTarget -Force | Out-Null
foreach ($file in @("ai-pack.lock.json", "ai-runtime.lock.json", "THIRD_PARTY_MODELS.md")) {
    Copy-Item -LiteralPath (Join-Path $repositoryRoot "packaging\$file") -Destination $packagingTarget
}
Copy-Item -LiteralPath (Join-Path $repositoryRoot "LICENSE") -Destination (Join-Path $companionRoot "LICENSE.txt")

# Pinned CPU runtimes for local voice (whisper-server) and the optional local model (llama-server).
Invoke-Native $Python @((Join-Path $PSScriptRoot "ai_pack.py"), "prepare-runtime", "--target", "windows-x64",
    "--cache", $CacheDirectory, "--runtime-output", (Join-Path $companionRoot "ai")) "The pinned AI runtimes could not be prepared."
# Keep only what the gateway starts: the two servers and their libraries.
foreach ($runtime in @(@{ Folder = "llama"; Keep = "llama-server.exe" }, @{ Folder = "whisper"; Keep = "whisper-server.exe" })) {
    $folder = Join-Path $companionRoot "ai\runtime\$($runtime.Folder)"
    if (-not (Test-Path -LiteralPath (Join-Path $folder $runtime.Keep))) { throw "Missing $($runtime.Keep) in $folder" }
    Get-ChildItem -LiteralPath $folder -File -Filter *.exe | Where-Object { $_.Name -ne $runtime.Keep } | Remove-Item
}

# Smoke checks on the frozen bundle (no window, no network).
Invoke-Native $executable @("voice-check", "--dependencies-only") "The frozen companion is missing microphone capture support."
Invoke-Native $executable @("pack", "status", "--root", $companionRoot, "--profile", "voice-only") "The frozen companion cannot read the AI pack lock."
Invoke-Native $executable @("runtime", "configure", "--help") "The frozen companion cannot host the AI gateway."

if ($VoicePackOutput) {
    # Offline voice pack: the same verified files the installer downloads, as one zip.
    $stage = Join-Path $WorkDirectory "voice-pack"
    if (Test-Path -LiteralPath $stage) { Remove-Item -LiteralPath $stage -Recurse -Force }
    New-Item -ItemType Directory -Path $stage -Force | Out-Null
    Copy-Item -LiteralPath (Join-Path $repositoryRoot "packaging") -Destination (Join-Path $stage "packaging") -Recurse
    $packArguments = @("pack", "install", "--profile", "voice-only", "--root", $stage)
    if ($ModelSourceDirectory) { $packArguments += @("--from-dir", $ModelSourceDirectory) }
    Invoke-Native $executable $packArguments "The voice pack could not be assembled."
    $VoicePackOutput = [IO.Path]::GetFullPath($VoicePackOutput)
    if (Test-Path -LiteralPath $VoicePackOutput) { Remove-Item -LiteralPath $VoicePackOutput }
    # tar.exe (Windows 10+) writes portable forward-slash entry names; .NET Framework's ZipFile does not.
    Invoke-Native "$env:SystemRoot\System32\tar.exe" @("-a", "-c", "-f", $VoicePackOutput, "-C", (Join-Path $stage "ai"), "models", "pack.json") "The voice pack zip could not be written."
    (Get-FileHash -LiteralPath $VoicePackOutput -Algorithm SHA256).Hash.ToLowerInvariant() + "  " + [IO.Path]::GetFileName($VoicePackOutput) |
        Set-Content -LiteralPath "$VoicePackOutput.sha256" -Encoding ASCII
}

$bytes = (Get-ChildItem -LiteralPath $companionRoot -Recurse -File | Measure-Object Length -Sum).Sum
[pscustomobject]@{
    Companion = $companionRoot
    Executable = $executable
    Bytes = $bytes
    VoicePack = $VoicePackOutput
}
