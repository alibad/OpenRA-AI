[CmdletBinding()]
param()

$ErrorActionPreference = "Stop"
$repositoryRoot = Split-Path -Parent $PSScriptRoot
$engineRoot = Join-Path $repositoryRoot "engine\openra"
$python = Join-Path $repositoryRoot ".venv\Scripts\python.exe"
$utility = Join-Path $engineRoot "bin\OpenRA.Utility.exe"
$paletteFile = Join-Path $engineRoot "mods\ra\maps\chernobyl\temperat.pal"
$staging = Join-Path $repositoryRoot "generated\red-sea-sprites"
$paletteDirectory = Join-Path $staging "palette"
$bits = Join-Path $engineRoot "mods\ra\bits"
$airAssets = @(
    "samad", "f15sa", "ah64sa", "f15sahusk", "ah64sahusk", "ah64sarotor",
    "redsea-air-muzzle", "redsea-air-impact", "samadicon", "f15saicon", "ah64saicon",
    "redsea-drone-impact"
)

foreach ($required in @($python, $utility, $paletteFile)) {
    if (-not (Test-Path -LiteralPath $required)) {
        throw "Missing required air-asset build input: $required"
    }
}

$resolvedStaging = [IO.Path]::GetFullPath($staging).TrimEnd('\')
foreach ($asset in $airAssets) {
    $assetDirectory = [IO.Path]::GetFullPath((Join-Path $staging $asset))
    if (-not $assetDirectory.StartsWith($resolvedStaging + '\', [StringComparison]::OrdinalIgnoreCase)) {
        throw "Refusing to clean air asset outside staging: $assetDirectory"
    }
    if (Test-Path -LiteralPath $assetDirectory) {
        Remove-Item -LiteralPath $assetDirectory -Recurse -Force
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

& $python (Join-Path $PSScriptRoot "build-red-sea-sprites.py") --palette $paletteReference.FullName
if ($LASTEXITCODE -ne 0) { throw "Red Sea sprite frame build failed." }

foreach ($asset in $airAssets) {
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
        $generatedShp = Join-Path $assetDirectory "redsea.shp"
    }
    if (-not (Test-Path -LiteralPath $generatedShp)) {
        throw "SHP conversion produced no package for $asset."
    }
    Copy-Item -LiteralPath $generatedShp -Destination (Join-Path $bits "$asset.shp") -Force
}

& $python (Join-Path $PSScriptRoot "generate-red-sea-sfx.py") --air-only --output $bits
if ($LASTEXITCODE -ne 0) { throw "Air-warfare sound-effect generation failed." }

Push-Location $engineRoot
try {
    & $utility ra --check-yaml
    if ($LASTEXITCODE -ne 0) { throw "OpenRA YAML validation failed." }
    & $utility ra --check-missing-sprites
    if ($LASTEXITCODE -ne 0) { throw "OpenRA missing-sprite validation failed." }
}
finally {
    Pop-Location
}

Write-Host "Red Sea air assets were clean-built and validated without touching missions." -ForegroundColor Green
