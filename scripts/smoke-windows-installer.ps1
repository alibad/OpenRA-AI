[CmdletBinding()]
param([string]$Version = "0.1.0-alpha.1")

$ErrorActionPreference = "Stop"
$repositoryRoot = Split-Path -Parent $PSScriptRoot
$artifactRoot = Join-Path $repositoryRoot "artifacts"
$releaseName = "OpenRA-AI-$Version-windows-x64"
$installer = Join-Path $artifactRoot "releases\$releaseName-setup.exe"
$checksumFile = "$installer.sha256"

foreach ($required in @($installer, $checksumFile)) {
    if (-not (Test-Path -LiteralPath $required)) {
        throw "Installer smoke-test input is missing: $required"
    }
}

$expected = (Get-Content -LiteralPath $checksumFile -Raw).Split(" ")[0].Trim().ToLowerInvariant()
$actual = (Get-FileHash -LiteralPath $installer -Algorithm SHA256).Hash.ToLowerInvariant()
if ($actual -ne $expected) {
    throw "Installer SHA-256 does not match its checksum file."
}

$artifactResolved = (Resolve-Path -LiteralPath $artifactRoot).Path
$testRoot = Join-Path $artifactResolved ("installer-smoke-" + [guid]::NewGuid().ToString("N"))
New-Item -ItemType Directory -Path $testRoot | Out-Null

try {
    $install = Start-Process -FilePath $installer -ArgumentList "/S", "/D=$testRoot" -Wait -PassThru
    if ($install.ExitCode -ne 0) {
        throw "The silent installer exited with code $($install.ExitCode)."
    }

    foreach ($required in @(
        (Join-Path $testRoot "Play-OpenRAAI.cmd"),
        (Join-Path $testRoot "bin\openra-ai-companion.exe"),
        (Join-Path $testRoot "engine\openra\bin\OpenRA-AI.exe"),
        (Join-Path $testRoot "assets\brand\rtsai.ico"),
        (Join-Path $testRoot "Uninstall OpenRA AI.exe")
    )) {
        if (-not (Test-Path -LiteralPath $required)) {
            throw "Installed package is missing: $required"
        }
    }

    $uninstaller = Join-Path $testRoot "Uninstall OpenRA AI.exe"
    $uninstall = Start-Process -FilePath $uninstaller -ArgumentList "/S", "_?=$testRoot" -Wait -PassThru
    if ($uninstall.ExitCode -ne 0) {
        throw "The silent uninstaller exited with code $($uninstall.ExitCode)."
    }
}
finally {
    if (Test-Path -LiteralPath $testRoot) {
        $testResolved = (Resolve-Path -LiteralPath $testRoot).Path
        if (-not $testResolved.StartsWith($artifactResolved + [IO.Path]::DirectorySeparatorChar)) {
            throw "Refusing to remove an installer smoke-test directory outside artifacts."
        }
        Remove-Item -LiteralPath $testResolved -Recurse -Force
    }
}

Write-Host "Windows setup installer smoke test passed." -ForegroundColor Green
