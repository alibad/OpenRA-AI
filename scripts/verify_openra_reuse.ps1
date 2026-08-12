[CmdletBinding()]
param()

$ErrorActionPreference = 'Stop'

$repoRoot = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
$engineRoot = Join-Path $repoRoot 'engine\openra'
$dotnet = Join-Path $repoRoot '.dotnet\dotnet.exe'
$python = Join-Path $repoRoot '.venv\Scripts\python.exe'
$artifactRoot = Join-Path $repoRoot '.artifacts\upstream-reuse\build'
$artifactMods = Join-Path $artifactRoot 'mods'
$engineMods = Join-Path $engineRoot 'mods'

if (-not (Test-Path -LiteralPath $dotnet -PathType Leaf))
{
	throw "Bundled .NET runtime not found: $dotnet"
}

if (-not (Test-Path -LiteralPath $python -PathType Leaf))
{
	throw "Workspace Python environment not found: $python"
}

New-Item -ItemType Directory -Path $artifactRoot -Force | Out-Null
if (-not (Test-Path -LiteralPath $artifactMods))
{
	New-Item -ItemType Junction -Path $artifactMods -Target $engineMods | Out-Null
}

Push-Location $engineRoot
try
{
	& $dotnet build 'OpenRA.Mods.Cnc\OpenRA.Mods.Cnc.csproj' --no-restore -c Debug -o $artifactRoot -p:WarningLevel=0
	if ($LASTEXITCODE -ne 0) { throw 'OpenRA.Mods.Cnc/OpenRA.Mods.Common build failed.' }

	& $dotnet build 'OpenRA.Mods.D2k\OpenRA.Mods.D2k.csproj' --no-restore -c Debug -o $artifactRoot -p:WarningLevel=0
	if ($LASTEXITCODE -ne 0) { throw 'OpenRA.Mods.D2k build failed.' }

	& $dotnet build 'OpenRA.Utility\OpenRA.Utility.csproj' --no-restore -c Debug -o $artifactRoot -p:WarningLevel=0
	if ($LASTEXITCODE -ne 0) { throw 'OpenRA.Utility build failed.' }

	$previousEngineDir = $env:ENGINE_DIR
	$env:ENGINE_DIR = $artifactRoot
	try
	{
		& $dotnet (Join-Path $artifactRoot 'OpenRA.Utility.dll') ra --check-yaml
		if ($LASTEXITCODE -ne 0) { throw 'RA MiniYAML validation failed.' }

		& $dotnet (Join-Path $artifactRoot 'OpenRA.Utility.dll') all --check-explicit-interfaces
		if ($LASTEXITCODE -ne 0) { throw 'Explicit interface validation failed.' }

		& $dotnet (Join-Path $artifactRoot 'OpenRA.Utility.dll') all --check-conditional-trait-interface-overrides
		if ($LASTEXITCODE -ne 0) { throw 'Conditional trait interface validation failed.' }
	}
	finally
	{
		$env:ENGINE_DIR = $previousEngineDir
	}
}
finally
{
	Pop-Location
}

Push-Location $repoRoot
try
{
	& $python 'scripts\openra_upstream_inventory.py' --check
	if ($LASTEXITCODE -ne 0) { throw 'Pinned upstream inventory check failed.' }

	& $python 'scripts\check_openra_reuse.py'
	if ($LASTEXITCODE -ne 0) { throw 'Reuse manifest and roadmap validation failed.' }
}
finally
{
	Pop-Location
}

Write-Host 'OpenRA upstream reuse verification passed.' -ForegroundColor Green
