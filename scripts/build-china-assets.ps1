[CmdletBinding()]
param(
    [switch]$RegenerateVoices,
    [switch]$SkipValidation
)

$ErrorActionPreference = "Stop"
$repositoryRoot = Split-Path -Parent $PSScriptRoot
$engineRoot = Join-Path $repositoryRoot "engine\openra"
$utility = Join-Path $engineRoot "bin\OpenRA.Utility.exe"
$paletteFile = Join-Path $engineRoot "mods\ra\maps\chernobyl\temperat.pal"
$staging = Join-Path $repositoryRoot "generated\china-faction-sprites"
$paletteDirectory = Join-Path $staging "palette"
$bits = Join-Path $engineRoot "mods\ra\bits"
$venvPython = Join-Path $repositoryRoot ".venv\Scripts\python.exe"
$python = if (Test-Path -LiteralPath $venvPython) { $venvPython } else { (Get-Command python).Source }

foreach ($required in @($python, $utility, $paletteFile)) {
    if (-not (Test-Path -LiteralPath $required)) { throw "Missing China asset build input: $required" }
}

New-Item -ItemType Directory -Path $paletteDirectory, $bits -Force | Out-Null
$env:ENGINE_DIR = $engineRoot
$env:DOTNET_ROLL_FORWARD = "Major"

Push-Location $paletteDirectory
try {
    & $utility ra --extract 2tnk.shp
    if ($LASTEXITCODE -ne 0) { throw "Palette sprite extraction failed." }
    & $utility ra --png .\2tnk.shp $paletteFile --noshadow
    if ($LASTEXITCODE -ne 0) { throw "Palette PNG export failed." }
}
finally { Pop-Location }

$paletteReference = Get-ChildItem -LiteralPath $paletteDirectory -Filter "2tnk-*.png" | Select-Object -First 1
if (-not $paletteReference) { throw "Palette export produced no indexed PNG frame." }

& $python (Join-Path $PSScriptRoot "build-china-ui.py")
if ($LASTEXITCODE -ne 0) { throw "China selector UI generation failed." }
& $python (Join-Path $PSScriptRoot "build-china-assets.py") --palette $paletteReference.FullName
if ($LASTEXITCODE -ne 0) { throw "China sprite generation failed." }

$assets = @(
    "cnrifle", "cnnetwork", "cnportable", "redspear",
    "cnqilin", "cnqilinhusk", "cnlynx", "cnlynxhusk", "cnzbd", "cnzbdhusk", "cnphl", "cnphlhusk",
    "cnskyspear", "cnskyspearhusk", "cncloud", "cncloudhusk", "cncrane", "cncranehusk", "cncranerotor",
    "cnluyang", "cnluyangturret", "cnluyangsink", "cnhaiwang", "cnhaiwangturret", "cnhaiwangsink",
    "china-heavy-muzzle", "china-light-muzzle", "china-missile", "china-drone-projectile",
    "china-network-pulse", "china-network-impact", "china-precision-impact", "china-naval-impact", "china-wake",
    "cnrifleicon", "cnnetworkicon", "cnportableicon", "redspearicon", "cnqilinicon", "cnlynxicon", "cnzbdicon",
    "cnphlicon", "cnskyspearicon", "cncloudicon", "cncraneicon", "cnluyangicon", "cnhaiwangicon"
)

foreach ($asset in $assets) {
    $assetDirectory = Join-Path $staging $asset
    Get-ChildItem -LiteralPath $assetDirectory -Filter "*.shp" -ErrorAction SilentlyContinue | Remove-Item -Force
    Push-Location $assetDirectory
    try {
        & $utility ra --shp "$asset-*.png"
        if ($LASTEXITCODE -ne 0) { throw "SHP conversion failed for $asset." }
    }
    finally { Pop-Location }
    $generatedShp = Get-ChildItem -LiteralPath $assetDirectory -Filter "*.shp" | Select-Object -First 1
    if (-not $generatedShp) { throw "SHP conversion produced no package for $asset." }
    Copy-Item -LiteralPath $generatedShp.FullName -Destination (Join-Path $bits "$asset.shp") -Force
}

& $python (Join-Path $PSScriptRoot "generate-china-sfx.py")
if ($LASTEXITCODE -ne 0) { throw "China sound-effect generation failed." }

if ($RegenerateVoices) {
    & $python (Join-Path $PSScriptRoot "generate-china-voices.py")
    if ($LASTEXITCODE -ne 0) { throw "China bilingual voice generation failed." }
}

& $python (Join-Path $PSScriptRoot "build-china-mission.py")
if ($LASTEXITCODE -ne 0) { throw "China mission packaging failed." }

if (-not $SkipValidation) {
    Push-Location $engineRoot
	try {
		$mission = Join-Path $repositoryRoot "generated\missions\haitan-network-2026.oramap"
		& $utility ra --check-yaml $mission
		if ($LASTEXITCODE -ne 0) { throw "China mission YAML validation failed." }
		& $utility ra --check-yaml
        if ($LASTEXITCODE -ne 0) { throw "China rules YAML validation failed." }
        & $utility ra --check-missing-sprites
        if ($LASTEXITCODE -ne 0) { throw "China sprite validation failed." }
    }
    finally { Pop-Location }
}

Write-Host "China faction assets built successfully." -ForegroundColor Green
