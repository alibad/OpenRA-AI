$ErrorActionPreference = "Stop"

$repoRoot = Split-Path -Parent $PSScriptRoot
$engineRoot = Join-Path $repoRoot "engine/openra"
$outputRoot = Join-Path $repoRoot ".codex-build/experience-composer"
$dotnetCandidates = @(
	"C:/Users/Admin/.dotnet/dotnet.exe",
	"C:/Program Files/dotnet/dotnet.exe",
	"dotnet"
)

$dotnet = $dotnetCandidates | Where-Object {
	try { & $_ --list-sdks 2>$null | Out-Null; $LASTEXITCODE -eq 0 }
	catch { $false }
} | Select-Object -First 1

if (-not $dotnet) {
	throw "A .NET SDK is required to verify the Experience Composer."
}

New-Item -ItemType Directory -Force -Path $outputRoot | Out-Null

Push-Location $engineRoot
try {
	& $dotnet build OpenRA.Mods.Common/OpenRA.Mods.Common.csproj --no-restore "-p:OutDir=$outputRoot/"
	if ($LASTEXITCODE -ne 0) { throw "OpenRA.Mods.Common build failed." }

	& $dotnet build OpenRA.Mods.Cnc/OpenRA.Mods.Cnc.csproj --no-restore "-p:OutDir=$outputRoot/"
	if ($LASTEXITCODE -ne 0) { throw "OpenRA.Mods.Cnc build failed." }

	& $dotnet build OpenRA.Utility/OpenRA.Utility.csproj --no-restore "-p:OutDir=$outputRoot/"
	if ($LASTEXITCODE -ne 0) { throw "OpenRA.Utility build failed." }

	$env:ENGINE_DIR = $engineRoot
	& "C:/Program Files/dotnet/dotnet.exe" "$outputRoot/OpenRA.Utility.dll" ra --check-yaml
	if ($LASTEXITCODE -ne 0) { throw "RA YAML validation failed." }
}
finally {
	Pop-Location
}

Write-Host "Experience Composer verification passed."
