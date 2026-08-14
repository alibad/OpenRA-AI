[CmdletBinding()]
param()

$ErrorActionPreference = "Stop"
$repositoryRoot = Split-Path -Parent $PSScriptRoot
$artifactRoot = Join-Path $repositoryRoot "artifacts\check"
$testRoot = Join-Path $artifactRoot "windows-launcher-bootstrap"
$bin = Join-Path $testRoot "engine\openra\bin"
$bootstrapDirectory = Join-Path $testRoot "apps\launcher"
$bootstrap = Join-Path $bootstrapDirectory "Start-OpenRAAI.ps1"
$resultPath = Join-Path $testRoot "bootstrap-result.json"
$originalCompanionMarker = $env:OPENRA_AI_COMPANION
$originalResultPath = $env:OPENRA_AI_BOOTSTRAP_TEST_RESULT

try {
    if (Test-Path -LiteralPath $testRoot) {
        $resolvedTestRoot = (Resolve-Path -LiteralPath $testRoot).Path
        $resolvedArtifactRoot = (Resolve-Path -LiteralPath $artifactRoot).Path
        if (-not $resolvedTestRoot.StartsWith($resolvedArtifactRoot + [IO.Path]::DirectorySeparatorChar)) {
            throw "Refusing to replace a launcher test directory outside artifacts."
        }
        Remove-Item -LiteralPath $resolvedTestRoot -Recurse -Force
    }

    New-Item -ItemType Directory -Path $bin, $bootstrapDirectory -Force | Out-Null
    & (Join-Path $PSScriptRoot "build-windows-launcher.ps1") -OutputDirectory $bin -SelfContained
    if ($LASTEXITCODE -ne 0) {
        throw "The branded launcher test build failed."
    }

    @'
param([string]$EncodedGameArguments)
$decoded = [Text.Encoding]::UTF8.GetString([Convert]::FromBase64String($EncodedGameArguments)) | ConvertFrom-Json
[ordered]@{
    arguments = @($decoded)
    bootstrap_invoked = $true
} | ConvertTo-Json | Set-Content -LiteralPath $env:OPENRA_AI_BOOTSTRAP_TEST_RESULT -Encoding UTF8
exit 23
'@ | Set-Content -LiteralPath $bootstrap -Encoding UTF8

    Remove-Item Env:OPENRA_AI_COMPANION -ErrorAction SilentlyContinue
    $env:OPENRA_AI_BOOTSTRAP_TEST_RESULT = $resultPath
    $launcher = Join-Path $bin "OpenRA-AI.exe"
    $process = Start-Process -FilePath $launcher `
        -ArgumentList @("Game.Mod=ra", "Launch.Map=bootstrap-test.oramap") `
        -WorkingDirectory $bin -PassThru -Wait
    if ($process.ExitCode -ne 23) {
        throw "The branded launcher did not return the companion bootstrap exit code."
    }
    if (-not (Test-Path -LiteralPath $resultPath)) {
        throw "The branded launcher did not invoke the companion bootstrap."
    }

    $result = Get-Content -LiteralPath $resultPath -Raw | ConvertFrom-Json
    if (-not $result.bootstrap_invoked -or $result.arguments.Count -ne 2 `
        -or $result.arguments[0] -ne "Game.Mod=ra" `
        -or $result.arguments[1] -ne "Launch.Map=bootstrap-test.oramap") {
        throw "The branded launcher did not preserve its game arguments through the companion bootstrap."
    }
}
finally {
    if ($null -eq $originalCompanionMarker) {
        Remove-Item Env:OPENRA_AI_COMPANION -ErrorAction SilentlyContinue
    }
    else {
        $env:OPENRA_AI_COMPANION = $originalCompanionMarker
    }
    if ($null -eq $originalResultPath) {
        Remove-Item Env:OPENRA_AI_BOOTSTRAP_TEST_RESULT -ErrorAction SilentlyContinue
    }
    else {
        $env:OPENRA_AI_BOOTSTRAP_TEST_RESULT = $originalResultPath
    }
    if (Test-Path -LiteralPath $testRoot) {
        $resolvedTestRoot = (Resolve-Path -LiteralPath $testRoot).Path
        $resolvedArtifactRoot = (Resolve-Path -LiteralPath $artifactRoot).Path
        if (-not $resolvedTestRoot.StartsWith($resolvedArtifactRoot + [IO.Path]::DirectorySeparatorChar)) {
            throw "Refusing to remove a launcher test directory outside artifacts."
        }
        Remove-Item -LiteralPath $resolvedTestRoot -Recurse -Force
    }
}

Write-Host "Branded Windows launcher companion bootstrap passed." -ForegroundColor Green
