[CmdletBinding()]
param(
    [switch]$SkipVoices
)

$ErrorActionPreference = "Stop"
$repositoryRoot = (Resolve-Path (Split-Path -Parent $PSScriptRoot)).Path
$engineRoot = Join-Path $repositoryRoot "engine\openra"
$python = Join-Path $repositoryRoot ".venv\Scripts\python.exe"
$utility = Join-Path $engineRoot "bin\OpenRA.Utility.exe"
$paletteFile = Join-Path $engineRoot "mods\ra\maps\chernobyl\temperat.pal"
$staging = Join-Path $repositoryRoot "generated\iran-sprites"
$paletteDirectory = Join-Path $staging "palette"
$bits = Join-Path $engineRoot "mods\ra\bits"

foreach ($required in @($python, $utility, $paletteFile)) {
    if (-not (Test-Path -LiteralPath $required)) {
        throw "Missing Iran asset build input: $required"
    }
}

# Clean only the dedicated generated frame tree after resolving it beneath the
# dedicated worktree.  Installed bits are overwritten by exact filename.
$resolvedParent = [System.IO.Path]::GetFullPath((Split-Path -Parent $staging))
$expectedParent = [System.IO.Path]::GetFullPath((Join-Path $repositoryRoot "generated"))
if ($resolvedParent -ne $expectedParent) {
    throw "Refusing to clean unexpected sprite directory: $staging"
}
if (Test-Path -LiteralPath $staging) {
    Remove-Item -LiteralPath $staging -Recurse -Force
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
if ($LASTEXITCODE -ne 0) { throw "Iran faction selector flag build failed." }

& $python (Join-Path $PSScriptRoot "build-iran-sprites.py") --palette $paletteReference.FullName
if ($LASTEXITCODE -ne 0) { throw "Iran sprite frame build failed." }

$assets = @(
    "irbas", "iratgm", "irdc", "shadowone",
    "irkarr", "irraad", "irfajr", "ircoast",
    "irazar", "irtoufan", "irmohajer", "irloiter", "irpey", "irghadir",
    "irkarrhusk", "irraadhusk", "irfajrhusk", "ircoasthusk",
    "irazarhusk", "irtoufanhusk", "irmohajerhusk", "irpeysink", "irghadirsink",
    "irtoufanrotor", "irmuzzle", "irimpact", "irsabotage", "ircloak", "irwake", "irmissile",
    "irbasicon", "iratgmicon", "irdcicon", "shadowoneicon",
    "irkarricon", "irraadicon", "irfajricon", "ircoasticon",
    "irazaricon", "irtoufanicon", "irmohajericon", "irloitericon", "irpeyicon", "irghadiricon"
)

foreach ($asset in $assets) {
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
    if (-not (Test-Path -LiteralPath $generatedShp)) {
        throw "SHP conversion produced no package for $asset."
    }
    Copy-Item -LiteralPath $generatedShp -Destination (Join-Path $bits "$asset.shp") -Force
}

& $python (Join-Path $PSScriptRoot "generate-iran-sfx.py")
if ($LASTEXITCODE -ne 0) { throw "Iran sound-effect generation failed." }

if (-not $SkipVoices) {
    & $python (Join-Path $PSScriptRoot "generate-iran-voices.py") --only-missing
    if ($LASTEXITCODE -ne 0) { throw "Iran bilingual voice generation failed." }
}

& $python (Join-Path $PSScriptRoot "build-iran-map.py")
if ($LASTEXITCODE -ne 0) { throw "Iran map packaging failed." }

Push-Location $engineRoot
try {
    & $utility ra --check-yaml (Join-Path $repositoryRoot "generated\missions\iran-doctrine-range.oramap")
    if ($LASTEXITCODE -ne 0) { throw "Iran skirmish map validation failed." }
    & $utility ra --check-missing-sprites
    if ($LASTEXITCODE -ne 0) { throw "Iran missing-sprite validation failed." }
}
finally {
    Pop-Location
}

Write-Host "Iran faction assets, audio, map, YAML, and sprite references are valid." -ForegroundColor Green
