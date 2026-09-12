[CmdletBinding()]
param(
    [string]$OutputDirectory,
    [string]$EngineRoot,
    [ValidateSet("Debug", "Release")]
    [string]$Configuration = "Release",
    [switch]$SelfContained
)

$ErrorActionPreference = "Stop"
$repositoryRoot = Split-Path -Parent $PSScriptRoot
if (-not $EngineRoot) { $engineRoot = Join-Path $repositoryRoot "engine\openra" }
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
    (Get-Command dotnet.exe -ErrorAction SilentlyContinue | Select-Object -ExpandProperty Source),
    (Join-Path $repositoryRoot ".dotnet\dotnet.exe"),
    (Join-Path $env:USERPROFILE ".dotnet\dotnet.exe")
)
$dotnet = $null
foreach ($candidate in $dotnetCandidates) {
    if ($candidate -and (Test-Path -LiteralPath $candidate)) {
        $version = (& $candidate --version).Trim()
        if ($LASTEXITCODE -eq 0 -and $version -match '^(\d+)\.' -and [int]$Matches[1] -ge 10) {
            $dotnet = $candidate
            break
        }
    }
}
if (-not $dotnet) {
    throw "The .NET 10 SDK or newer is required to build the OpenRA AI launcher."
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
