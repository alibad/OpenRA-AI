[CmdletBinding()]
param([switch]$FullEngine)

$ErrorActionPreference = "Stop"
$repositoryRoot = Split-Path -Parent $PSScriptRoot
$workflowPath = Join-Path $repositoryRoot ".github\workflows"

if (Test-Path -LiteralPath $workflowPath) {
    throw "Hosted GitHub workflows are not allowed in this repository."
}

$requiredPaths = @(
    "README.md",
    "docs\architecture.md",
    "docs\earth-missions.md",
    "apps\launcher\Start-OpenRAAI.ps1",
    "apps\web",
    "services\companion",
    "services\worldgen",
    "packages\contracts",
    "packages\openra-adapter",
    "engine\openra"
)

foreach ($requiredPath in $requiredPaths) {
    if (-not (Test-Path -LiteralPath (Join-Path $repositoryRoot $requiredPath))) {
        throw "Required repository path is missing: $requiredPath"
    }
}

$python = Join-Path $repositoryRoot ".venv\Scripts\python.exe"
if (-not (Test-Path -LiteralPath $python)) {
    throw "Python environment is missing. Run scripts\setup.ps1 first."
}

# Keep the validation command reproducible even when the virtual environment
# was created before the local packages were installed in editable mode.
$sourcePaths = @(
    (Join-Path $repositoryRoot "services\worldgen\src"),
    (Join-Path $repositoryRoot "services\companion\src")
)
if ($env:PYTHONPATH) {
    $sourcePaths += $env:PYTHONPATH
}
$env:PYTHONPATH = $sourcePaths -join [IO.Path]::PathSeparator

& $python -m openra_ai_companion.cli voice-check --dependencies-only
if ($LASTEXITCODE -ne 0) {
    throw "Local voice capture dependencies are missing. Run scripts\setup.ps1 again."
}

# Faction and theater fixtures intentionally exercise the complete built-in
# portfolio. Point OpenRA.Utility at disposable settings now that new installs
# correctly default to AI Assistant Only.
$originalSupportDir = $env:SUPPORT_DIR
$originalUtilityExperienceProfile = $env:OPENRA_UTILITY_EXPERIENCE_PROFILE
$testSettingsDirectory = Join-Path $repositoryRoot "artifacts\check\support"
$testSettingsFile = Join-Path $testSettingsDirectory "settings.yaml"
New-Item -ItemType Directory -Path $testSettingsDirectory -Force | Out-Null
@"
Experience@ra:
	Profile: world-war-iii
"@ | Set-Content -LiteralPath $testSettingsFile -Encoding UTF8
$env:SUPPORT_DIR = $testSettingsDirectory
$env:OPENRA_UTILITY_EXPERIENCE_PROFILE = "world-war-iii"

& $python -m py_compile (Join-Path $repositoryRoot "scripts\release.py") (Join-Path $repositoryRoot "scripts\ai_pack.py")
if ($LASTEXITCODE -ne 0) { throw "Release framework compilation failed." }
& $python (Join-Path $repositoryRoot "scripts\ai_pack.py") validate
if ($LASTEXITCODE -ne 0) { throw "AI pack lock validation failed." }

Push-Location $repositoryRoot
try {
    git diff --check HEAD
    if ($LASTEXITCODE -ne 0) { throw "Git whitespace validation failed." }

    & (Join-Path $PSScriptRoot "prepare-test-fixtures.ps1")
    if ($LASTEXITCODE -ne 0) { throw "Test fixture preparation failed." }

    & $python -m unittest discover -s services\worldgen\tests -v
    if ($LASTEXITCODE -ne 0) { throw "Worldgen tests failed." }
    & $python -m unittest discover -s services\companion\tests -v
    if ($LASTEXITCODE -ne 0) { throw "Companion tests failed." }
    & $python -m unittest discover -s services\companion\evals -v
    if ($LASTEXITCODE -ne 0) { throw "Companion gameplay-agent evals failed." }
    & $python -m compileall -q services\worldgen\src services\companion\src
    if ($LASTEXITCODE -ne 0) { throw "Python compilation failed." }

    Push-Location apps\web
    try {
        npm run lint
        if ($LASTEXITCODE -ne 0) { throw "Web lint failed." }
        npm test
        if ($LASTEXITCODE -ne 0) { throw "Web tests failed." }
        npm audit --omit=dev
        if ($LASTEXITCODE -ne 0) { throw "Production dependency audit failed." }
        $webMap = Join-Path $repositoryRoot "artifacts\check\browser-riyadh-crossing-42.oramap"
        New-Item -ItemType Directory -Path (Split-Path -Parent $webMap) -Force | Out-Null
        npx tsx tests\build-openra-fixture.ts $webMap
        if ($LASTEXITCODE -ne 0) { throw "Browser mission fixture generation failed." }
    }
    finally {
        Pop-Location
    }

    $userDotnet = Join-Path $env:USERPROFILE ".dotnet"
    if (Test-Path -LiteralPath (Join-Path $userDotnet "dotnet.exe")) {
        $env:PATH = "$userDotnet;$env:PATH"
        $env:DOTNET_ROOT = $userDotnet
    }
    $env:DOTNET_ROLL_FORWARD = "Major"

    Push-Location engine\openra
    try {
        dotnet build OpenRA.sln -c Release --nologo --no-restore -p:TargetPlatform=win-x64
        if ($LASTEXITCODE -ne 0) { throw "OpenRA build failed." }
        dotnet test OpenRA.Test\OpenRA.Test.csproj -c Release --no-restore --nologo -p:TargetPlatform=win-x64
        if ($LASTEXITCODE -ne 0) { throw "OpenRA tests failed." }
        if ($FullEngine) {
            $env:ENGINE_DIR = (Get-Location).Path
            .\bin\OpenRA.Utility.exe ra --check-yaml
            if ($LASTEXITCODE -ne 0) { throw "OpenRA Red Alert rules validation failed." }
        }
    }
    finally {
        Pop-Location
    }

    & (Join-Path $PSScriptRoot "test-windows-launcher-bootstrap.ps1")
    if ($LASTEXITCODE -ne 0) { throw "Branded launcher companion bootstrap failed." }

    $checkOutput = Join-Path $repositoryRoot "artifacts\check"
    & $python -m openra_ai_worldgen.cli generate --lat 24.7136 --lon 46.6753 --title "Riyadh Crossing Check" --seed 42 --fixture services\worldgen\tests\fixtures\overpass-river.json --output $checkOutput
    if ($LASTEXITCODE -ne 0) { throw "Mission smoke generation failed." }
    $map = Join-Path $checkOutput "riyadh-crossing-check-42.oramap"

    Push-Location engine\openra
    try {
        $env:ENGINE_DIR = (Get-Location).Path
        .\bin\OpenRA.Utility.exe ra --check-yaml $map
        if ($LASTEXITCODE -ne 0) { throw "Generated mission failed OpenRA validation." }
        .\bin\OpenRA.Utility.exe ra --map-hash $map
        if ($LASTEXITCODE -ne 0) { throw "Generated mission hashing failed." }
        .\bin\OpenRA.Utility.exe ra --check-yaml $webMap
        if ($LASTEXITCODE -ne 0) { throw "Browser-generated mission failed OpenRA validation." }
        .\bin\OpenRA.Utility.exe ra --map-hash $webMap
        if ($LASTEXITCODE -ne 0) { throw "Browser-generated mission hashing failed." }
    }
    finally {
        Pop-Location
    }
}
finally {
    Pop-Location
    $env:SUPPORT_DIR = $originalSupportDir
    $env:OPENRA_UTILITY_EXPERIENCE_PROFILE = $originalUtilityExperienceProfile
}

Write-Host "OpenRA AI local checks passed." -ForegroundColor Green
