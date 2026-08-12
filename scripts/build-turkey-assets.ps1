[CmdletBinding()]
param(
	[switch]$RegenerateVoices,
	[switch]$SkipValidation
)

$ErrorActionPreference = "Stop"
$repositoryRoot = (Resolve-Path (Split-Path -Parent $PSScriptRoot)).Path
$engineRoot = Join-Path $repositoryRoot "engine\openra"
$python = Join-Path $repositoryRoot ".venv\Scripts\python.exe"
$dotnet = Join-Path $repositoryRoot "generated\tooling\dotnet\dotnet.exe"
$utility = Join-Path $engineRoot "bin\OpenRA.Utility.dll"
$paletteFile = Join-Path $engineRoot "mods\ra\maps\chernobyl\temperat.pal"
$staging = Join-Path $repositoryRoot "generated\turkey-sprites"
$paletteDirectory = Join-Path $staging "palette"
$bits = Join-Path $engineRoot "mods\ra\bits"
$telemetryDirectory = Join-Path $repositoryRoot "artifacts\turkey-faction"

foreach ($required in @($python, $dotnet, $utility, $paletteFile)) {
	if (-not (Test-Path -LiteralPath $required)) { throw "Missing Turkey asset build input: $required" }
}

# A clean build deletes only the dedicated Turkey staging directory. Resolve
# and verify its parent before recursive deletion so no broad path can be used.
$generatedRoot = (Resolve-Path (Join-Path $repositoryRoot "generated")).Path
$expectedStaging = Join-Path $generatedRoot "turkey-sprites"
if ([System.IO.Path]::GetFullPath($staging) -ne [System.IO.Path]::GetFullPath($expectedStaging)) {
	throw "Refusing to clean unexpected staging path: $staging"
}
if (Test-Path -LiteralPath $staging) { Remove-Item -LiteralPath $staging -Recurse -Force }
New-Item -ItemType Directory -Path $paletteDirectory, $bits, $telemetryDirectory -Force | Out-Null

$env:ENGINE_DIR = $engineRoot
$env:DOTNET_ROLL_FORWARD = "Major"

Push-Location $paletteDirectory
try {
	& $dotnet $utility ra --extract 2tnk.shp
	if ($LASTEXITCODE -ne 0) { throw "Palette sprite extraction failed." }
	& $dotnet $utility ra --png .\2tnk.shp $paletteFile --noshadow
	if ($LASTEXITCODE -ne 0) { throw "Palette PNG export failed." }
}
finally { Pop-Location }

$paletteReference = Get-ChildItem -LiteralPath $paletteDirectory -Filter "2tnk-*.png" | Select-Object -First 1
if (-not $paletteReference) { throw "Palette export produced no indexed PNG frame." }

& $python (Join-Path $PSScriptRoot "build-red-sea-ui.py")
if ($LASTEXITCODE -ne 0) { throw "Turkey selector flag generation failed." }
& $python (Join-Path $PSScriptRoot "build-turkey-sprites.py") --palette $paletteReference.FullName
if ($LASTEXITCODE -ne 0) { throw "Turkey sprite generation failed." }

$assets = @(
	"bozkir", "bozkirhusk", "aras8", "aras8husk", "yildirim", "yildirimhusk",
	"gokkalkan", "gokkalkanhusk", "sancak", "sancakhusk", "denizkaplan", "denizkaplanhusk",
	"kuzgunm", "kuzgunmhusk", "turnaah", "turnaahhusk", "sahinx", "sahinxhusk",
	"marmara", "marmarasink", "ege", "egesink", "poyraz", "poyrazsink",
	"trrifle", "trat", "trdroneop", "greywolf",
	"bozkiricon", "aras8icon", "yildirimicon", "gokkalkanicon", "sancakicon", "denizkaplanicon",
	"kuzgunmicon", "turnaahicon", "sahinxicon", "marmaraicon", "egeicon", "poyrazicon",
	"trrifleicon", "traticon", "trdroneopicon", "greywolficon", "turnaahrotor",
	"turkey-ground-muzzle", "turkey-air-muzzle", "turkey-designator", "turkey-wake",
	"turkey-at-impact", "turkey-heavy-impact", "turkey-artillery-impact", "turkey-air-impact", "turkey-naval-impact"
)

foreach ($asset in $assets) {
	$assetDirectory = Join-Path $staging $asset
	Push-Location $assetDirectory
	try {
		& $dotnet $utility ra --shp "$asset-*.png"
		if ($LASTEXITCODE -ne 0) { throw "SHP conversion failed for $asset." }
		$generatedShp = Get-ChildItem -LiteralPath $assetDirectory -Filter "*.shp" | Select-Object -First 1
		if (-not $generatedShp) { throw "SHP conversion produced no package for $asset." }
		Copy-Item -LiteralPath $generatedShp.FullName -Destination (Join-Path $bits "$asset.shp") -Force
	}
	finally { Pop-Location }
}

& $python (Join-Path $PSScriptRoot "generate-turkey-sfx.py")
if ($LASTEXITCODE -ne 0) { throw "Turkey sound-effect generation failed." }
if ($RegenerateVoices) {
	& $python (Join-Path $PSScriptRoot "generate-turkey-voices.py")
	if ($LASTEXITCODE -ne 0) { throw "Turkey bilingual voice generation failed." }
}
& $python (Join-Path $PSScriptRoot "build-turkey-mission.py")
if ($LASTEXITCODE -ne 0) { throw "Straits Shield mission packaging failed." }

if (-not $SkipValidation) {
	Push-Location $engineRoot
	try {
		& $dotnet $utility ra --check-yaml
		if ($LASTEXITCODE -ne 0) { throw "Turkey YAML validation failed." }
		& $dotnet $utility ra --check-missing-sprites
		if ($LASTEXITCODE -ne 0) { throw "Turkey missing-sprite validation failed." }
	}
	finally { Pop-Location }
	& $python -m unittest services.worldgen.tests.test_turkey_faction -v
	if ($LASTEXITCODE -ne 0) { throw "Turkey faction unit tests failed." }
}

$frameCounts = @{}
foreach ($asset in $assets) {
	$frameCounts[$asset] = @(Get-ChildItem -LiteralPath (Join-Path $staging $asset) -Filter "$asset-*.png").Count
}
$telemetry = [ordered]@{
	schema = "openra-ai.turkey-assets/v1"
	generated_at = (Get-Date).ToUniversalTime().ToString("o")
	branch = (git -C $repositoryRoot branch --show-current)
	engine_commit = (git -C $engineRoot rev-parse HEAD)
	asset_packages = $assets.Count
	frame_counts = $frameCounts
	mission_sha256 = (Get-FileHash (Join-Path $repositoryRoot "generated\missions\straits-shield-2026.oramap") -Algorithm SHA256).Hash.ToLowerInvariant()
	validation = if ($SkipValidation) { "skipped" } else { "passed" }
}
$telemetry | ConvertTo-Json -Depth 5 | Set-Content -LiteralPath (Join-Path $telemetryDirectory "asset-build-telemetry.json") -Encoding UTF8
Write-Host "Turkey faction assets and Straits Shield are built." -ForegroundColor Green
