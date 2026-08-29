[CmdletBinding()]
param(
    [string]$Version = "0.1.0-alpha.1",
    [int]$BridgePort = 10038,
    [int]$AIConsolePort = 10039,
    [int]$WorldStudioPort = 10040,
    [switch]$RequireAI,
    [switch]$RequireSignatures,
    [switch]$KeepExtracted
)

$ErrorActionPreference = "Stop"
$repositoryRoot = Split-Path -Parent $PSScriptRoot
$artifactRoot = Join-Path $repositoryRoot "artifacts"
$releaseName = "OpenRA-AI-$Version-windows-x64"
$archive = Join-Path $artifactRoot "releases\$releaseName.zip"
$checksumFile = "$archive.sha256"
$python = Join-Path $repositoryRoot ".venv\Scripts\python.exe"
$verify = Join-Path $PSScriptRoot "verify-live-match.py"
$signingScript = Join-Path $PSScriptRoot "sign-windows-artifacts.ps1"
$signaturesRequired = $RequireSignatures -or $env:OPENRA_AI_OFFICIAL_RELEASE -eq "1"

foreach ($required in @($archive, $checksumFile, $python, $verify)) {
    if (-not (Test-Path -LiteralPath $required)) {
        throw "Required smoke-test input is missing: $required"
    }
}

$expected = (Get-Content -LiteralPath $checksumFile -Raw).Split(" ")[0].Trim().ToLowerInvariant()
$actual = (Get-FileHash -LiteralPath $archive -Algorithm SHA256).Hash.ToLowerInvariant()
if ($actual -ne $expected) {
    throw "Package SHA-256 does not match its checksum file."
}

$artifactResolved = (Resolve-Path -LiteralPath $artifactRoot).Path
$testRoot = Join-Path $artifactResolved ("package-smoke-" + [guid]::NewGuid().ToString("N"))
New-Item -ItemType Directory -Path $testRoot | Out-Null
$launcherProcess = $null
$packageRoot = $null

try {
    Expand-Archive -LiteralPath $archive -DestinationPath $testRoot
    $packageRoot = Join-Path $testRoot $releaseName
    $launcher = Join-Path $packageRoot "apps\launcher\Start-OpenRAAI.ps1"
    $map = Join-Path $packageRoot "generated\missions\riyadh-crossing-42.oramap"
    foreach ($required in @(
        $launcher,
        $map,
        (Join-Path $packageRoot "Play-OpenRAAI.cmd"),
        (Join-Path $packageRoot "bin\openra-ai-companion.exe"),
        (Join-Path $packageRoot "engine\openra\bin\OpenRA-AI.exe")
    )) {
        if (-not (Test-Path -LiteralPath $required)) {
            throw "Portable package is missing: $required"
        }
    }

    if ($signaturesRequired) {
        & $signingScript -Paths @(
            (Join-Path $packageRoot "bin\openra-ai-companion.exe"),
            (Join-Path $packageRoot "bin\openra-ai-runtime.exe"),
            (Join-Path $packageRoot "engine\openra\bin\OpenRA-AI.exe"),
            (Join-Path $packageRoot "engine\openra\bin\OpenRA.exe"),
            (Join-Path $packageRoot "engine\openra\bin\OpenRA.Server.exe"),
            (Join-Path $packageRoot "engine\openra\bin\OpenRA.Utility.exe")
        ) -RequireSignatures -VerifyOnly
    }

    $launcherArguments = @(
        "-NoProfile",
        "-ExecutionPolicy", "Bypass",
        "-File", $launcher,
        "-Map", $map,
        "-Headless",
        "-NoSpeech",
        "-BridgePort", "$BridgePort",
        "-AIConsolePort", "$AIConsolePort",
        "-WorldStudioPort", "$WorldStudioPort"
    )
    $launcherProcess = Start-Process -FilePath "powershell.exe" -ArgumentList $launcherArguments `
        -WorkingDirectory $packageRoot -WindowStyle Hidden -PassThru

    $verifyArguments = @(
        $verify,
        "--bridge", "127.0.0.1:$BridgePort",
        "--ai-console", "http://127.0.0.1:$AIConsolePort",
        "--world-studio", "http://127.0.0.1:$WorldStudioPort",
        "--timeout", "60"
    )
    if ($RequireAI) {
        $verifyArguments += "--require-ai"
    }
    & $python @verifyArguments
    if ($LASTEXITCODE -ne 0) {
        throw "The packaged live-match verification failed."
    }
}
finally {
    if ($packageRoot) {
        $owned = @(Get-CimInstance Win32_Process | Where-Object {
            $_.ExecutablePath -and $_.ExecutablePath.StartsWith($packageRoot, [StringComparison]::OrdinalIgnoreCase)
        })
        foreach ($process in $owned) {
            Stop-Process -Id $process.ProcessId -Force -ErrorAction SilentlyContinue
        }
    }
    if ($launcherProcess -and -not $launcherProcess.HasExited) {
        if (-not $launcherProcess.WaitForExit(3000)) {
            Stop-Process -Id $launcherProcess.Id -Force -ErrorAction SilentlyContinue
        }
    }
    if (-not $KeepExtracted -and (Test-Path -LiteralPath $testRoot)) {
        $testResolved = (Resolve-Path -LiteralPath $testRoot).Path
        if (-not $testResolved.StartsWith($artifactResolved + [IO.Path]::DirectorySeparatorChar)) {
            throw "Refusing to remove a smoke-test directory outside artifacts."
        }
        Remove-Item -LiteralPath $testResolved -Recurse -Force
    }
}

Write-Host "Portable Windows package smoke test passed." -ForegroundColor Green
