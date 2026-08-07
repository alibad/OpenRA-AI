$ErrorActionPreference = "Stop"

$repositoryRoot = Split-Path -Parent $PSScriptRoot
$workflowPath = Join-Path $repositoryRoot ".github\workflows"

if (Test-Path -LiteralPath $workflowPath) {
    throw "Hosted GitHub workflows are not allowed in this repository."
}

$requiredPaths = @(
    "README.md",
    "docs\architecture.md",
    "docs\earth-missions.md",
    "apps\launcher",
    "apps\web",
    "services\companion",
    "services\worldgen",
    "packages\contracts",
    "packages\openra-adapter",
    "engine"
)

foreach ($requiredPath in $requiredPaths) {
    $absolutePath = Join-Path $repositoryRoot $requiredPath
    if (-not (Test-Path -LiteralPath $absolutePath)) {
        throw "Required repository path is missing: $requiredPath"
    }
}

Push-Location $repositoryRoot
try {
    git diff --check
    if ($LASTEXITCODE -ne 0) {
        throw "Git whitespace validation failed."
    }
}
finally {
    Pop-Location
}

Write-Host "OpenRA AI local checks passed."

