[CmdletBinding()]
param(
    [switch]$RegenerateVoices
)

$ErrorActionPreference = "Stop"
$repositoryRoot = Split-Path -Parent $PSScriptRoot
$engineRoot = Join-Path $repositoryRoot "engine\openra"
$python = Join-Path $repositoryRoot ".venv\Scripts\python.exe"
$utility = Join-Path $engineRoot "bin\OpenRA.Utility.exe"
$paletteFile = Join-Path $engineRoot "mods\ra\maps\chernobyl\temperat.pal"
$staging = Join-Path $repositoryRoot "generated\red-sea-sprites"
$paletteDirectory = Join-Path $staging "palette"
$bits = Join-Path $engineRoot "mods\ra\bits"

foreach ($required in @($python, $utility, $paletteFile)) {
    if (-not (Test-Path -LiteralPath $required)) {
        throw "Missing required Red Sea asset build input: $required"
    }
}

New-Item -ItemType Directory -Path $paletteDirectory, $bits -Force | Out-Null
$env:ENGINE_DIR = ".."
$env:DOTNET_ROLL_FORWARD = "Major"

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
if (-not $paletteReference) {
    throw "Palette export produced no indexed PNG frames."
}

& $python (Join-Path $PSScriptRoot "build-red-sea-ui.py")
if ($LASTEXITCODE -ne 0) { throw "Red Sea faction UI build failed." }

& $python (Join-Path $PSScriptRoot "build-red-sea-sprites.py") --palette $paletteReference.FullName
if ($LASTEXITCODE -ne 0) { throw "Red Sea sprite frame build failed." }

foreach ($asset in @(
    "m1a2s", "sads", "tech", "ymlr", "samad",
    "m1a2shusk", "sadshusk", "techhusk", "ymlrhusk",
    "m1a2sicon", "sadsicon", "techicon", "ymlricon", "samadicon",
    "redsea-m1-impact", "redsea-m1-muzzle", "redsea-drone-impact"
)) {
    $assetDirectory = Join-Path $staging $asset
    Push-Location $assetDirectory
    try {
        & $utility ra --shp "$asset-*.png"
        if ($LASTEXITCODE -ne 0) { throw "SHP conversion failed for $asset." }
    }
    finally {
        Pop-Location
    }
    $generatedShp = Join-Path $assetDirectory "$asset.shp"
    if (-not (Test-Path -LiteralPath $generatedShp) -and $asset.StartsWith("redsea-")) {
        # OpenRA.Utility derives its output name from the first hyphen-delimited
        # frame prefix, so both Red Sea effect packages are emitted as redsea.shp.
        $generatedShp = Join-Path $assetDirectory "redsea.shp"
    }
    if (-not (Test-Path -LiteralPath $generatedShp)) {
        throw "SHP conversion produced no package for $asset."
    }
    Copy-Item -LiteralPath $generatedShp -Destination (Join-Path $bits "$asset.shp") -Force
}

& $python (Join-Path $PSScriptRoot "generate-red-sea-sfx.py")
if ($LASTEXITCODE -ne 0) { throw "Red Sea sound-effect generation failed." }

if ($RegenerateVoices) {
    & $python (Join-Path $PSScriptRoot "generate-red-sea-voices.py")
    if ($LASTEXITCODE -ne 0) { throw "Red Sea bilingual voice generation failed." }
}

& $python (Join-Path $PSScriptRoot "build-red-sea-mission.py")
if ($LASTEXITCODE -ne 0) { throw "Red Sea mission packaging failed." }

Push-Location $engineRoot
try {
    foreach ($missionName in @(
        "jizan-corridor-2026.oramap",
        "hodeidah-lifeline-2026.oramap",
        "bab-al-mandab-passage-2026.oramap"
    )) {
        $mission = Join-Path $repositoryRoot "generated\missions\$missionName"
        & $utility ra --check-yaml $mission
        if ($LASTEXITCODE -ne 0) { throw "Red Sea mission validation failed for $missionName." }
    }
    & $utility ra --check-missing-sprites
    if ($LASTEXITCODE -ne 0) { throw "Red Sea sprite validation failed." }
}
finally {
    Pop-Location
}

Write-Host "Red Sea 2026 assets and mission are built and validated." -ForegroundColor Green
