[CmdletBinding()]
param()

$ErrorActionPreference = "Stop"
$repositoryRoot = (Resolve-Path (Split-Path -Parent $PSScriptRoot)).Path
$engineRoot = Join-Path $repositoryRoot "engine\openra"
$python = Join-Path $repositoryRoot ".venv\Scripts\python.exe"
$utility = Join-Path $engineRoot "bin\OpenRA.Utility.exe"
$paletteFile = Join-Path $engineRoot "mods\ra\maps\chernobyl\temperat.pal"
$paletteDirectory = Join-Path $repositoryRoot "generated\test-palette"

foreach ($required in @($python, $utility, $paletteFile)) {
    if (-not (Test-Path -LiteralPath $required)) {
        throw "Missing test fixture build input: $required"
    }
}

New-Item -ItemType Directory -Path $paletteDirectory -Force | Out-Null
$env:ENGINE_DIR = $engineRoot
$env:DOTNET_ROLL_FORWARD = "Major"

$paletteReference = Get-ChildItem -LiteralPath $paletteDirectory -Filter "2tnk-*.png" | Select-Object -First 1
if (-not $paletteReference) {
    Push-Location $paletteDirectory
    try {
        & $utility ra --extract 2tnk.shp
        if ($LASTEXITCODE -ne 0) { throw "Palette sprite extraction failed." }
        & $utility ra --png .\2tnk.shp $paletteFile --noshadow
        if ($LASTEXITCODE -ne 0) { throw "Palette PNG export failed." }
    }
    finally {
        Pop-Location
    }
    $paletteReference = Get-ChildItem -LiteralPath $paletteDirectory -Filter "2tnk-*.png" | Select-Object -First 1
}

if (-not $paletteReference) {
    throw "Palette export produced no indexed PNG frame."
}

foreach ($builder in @(
    "build-red-sea-sprites.py",
    "build-turkey-sprites.py",
    "build-china-assets.py",
    "build-iran-sprites.py"
)) {
    & $python (Join-Path $PSScriptRoot $builder) --palette $paletteReference.FullName
    if ($LASTEXITCODE -ne 0) { throw "Test sprite fixture build failed: $builder" }
}

foreach ($builder in @(
    "build-red-sea-mission.py",
    "build-turkey-mission.py",
    "build-china-mission.py",
    "build-iran-map.py"
)) {
    & $python (Join-Path $PSScriptRoot $builder) --skip-install
    if ($LASTEXITCODE -ne 0) { throw "Test mission fixture build failed: $builder" }
}

Write-Host "Generated faction and mission test fixtures." -ForegroundColor Green
