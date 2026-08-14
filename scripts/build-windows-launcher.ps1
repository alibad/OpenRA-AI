[CmdletBinding()]
param(
    [string]$OutputDirectory,
    [ValidateSet("Debug", "Release")]
    [string]$Configuration = "Release",
    [switch]$SelfContained
)

$ErrorActionPreference = "Stop"
$repositoryRoot = Split-Path -Parent $PSScriptRoot
$engineRoot = Join-Path $repositoryRoot "engine\openra"
$project = Join-Path $engineRoot "OpenRA.WindowsLauncher\OpenRA.WindowsLauncher.csproj"
$brandIcon = Join-Path $repositoryRoot "assets\brand\rtsai.ico"

if ([string]::IsNullOrWhiteSpace($OutputDirectory)) {
    $OutputDirectory = Join-Path $engineRoot "bin"
}

foreach ($required in @($project, $brandIcon)) {
    if (-not (Test-Path -LiteralPath $required)) {
        throw "Branded launcher input is missing: $required"
    }
}

$dotnetCandidates = @(
    (Join-Path $repositoryRoot ".dotnet\dotnet.exe"),
    (Join-Path $env:USERPROFILE ".dotnet\dotnet.exe")
)
$dotnet = $dotnetCandidates | Where-Object { Test-Path -LiteralPath $_ } | Select-Object -First 1
if (-not $dotnet) {
    $dotnetCommand = Get-Command dotnet.exe -ErrorAction SilentlyContinue
    $dotnet = if ($dotnetCommand) { $dotnetCommand.Source } else { $null }
}
if (-not $dotnet) {
    throw "A compatible .NET SDK is required to build the OpenRA AI launcher."
}

New-Item -ItemType Directory -Path $OutputDirectory -Force | Out-Null
$publishArguments = @(
    "publish",
    $project,
    "-c", $Configuration,
    "--nologo",
    "-r", "win-x64",
    "--self-contained", $(if ($SelfContained) { "true" } else { "false" }),
    "-p:TargetPlatform=win-x64",
    "-p:LauncherName=OpenRA-AI",
    "-p:LauncherIcon=$brandIcon",
    "-p:ModID=ra",
    "-p:DisplayName=OpenRA AI",
    "-p:FaqUrl=https://github.com/alibad/OpenRA-AI",
    "-p:CompanionBootstrap=true",
    "-p:PublishDir=$OutputDirectory"
)

& $dotnet @publishArguments
if ($LASTEXITCODE -ne 0) {
    throw "The branded Windows launcher build failed with exit code $LASTEXITCODE."
}

$launcher = Join-Path $OutputDirectory "OpenRA-AI.exe"
if (-not (Test-Path -LiteralPath $launcher)) {
    throw "The branded Windows launcher was not created: $launcher"
}

Write-Host "Branded OpenRA AI launcher ready: $launcher" -ForegroundColor Green
