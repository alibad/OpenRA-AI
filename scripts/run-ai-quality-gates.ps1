param(
    [switch]$FullMissions,
    [int]$MissionMaxTicks = 30000
)

$ErrorActionPreference = 'Stop'
$Workspace = Split-Path -Parent $PSScriptRoot
$Python = Join-Path $Workspace '.venv\Scripts\python.exe'
$DotNet = 'C:\Users\Admin\.dotnet\dotnet.exe'
$BuildOutput = Join-Path $Workspace 'artifacts\quality-gates\build'
$ReportPath = Join-Path $Workspace 'artifacts\quality-gates\latest.json'
$StartedAt = [DateTimeOffset]::UtcNow
$Gates = @()

function Invoke-Gate {
    param([string]$Name, [scriptblock]$Command)
    $started = [DateTimeOffset]::UtcNow
    & $Command
    $exitCode = $LASTEXITCODE
    if ($null -eq $exitCode) { $exitCode = 0 }
    $script:Gates += [ordered]@{
        name = $Name
        passed = $exitCode -eq 0
        exit_code = $exitCode
        seconds = [Math]::Round(([DateTimeOffset]::UtcNow - $started).TotalSeconds, 3)
    }
    if ($exitCode -ne 0) { throw "Quality gate '$Name' failed with exit code $exitCode." }
}

try {
    Invoke-Gate 'python-compile' { & $Python -m compileall -q (Join-Path $Workspace 'services\companion\src') }
    Invoke-Gate 'companion-tests' { & $Python -m unittest discover -s (Join-Path $Workspace 'services\companion\tests') -q }
    Invoke-Gate 'mission-inventory-tests' { & $Python -m unittest discover -s (Join-Path $Workspace 'services\companion\evals') -p 'test_mission_eval.py' -q }
    Invoke-Gate 'engine-build' {
        & $DotNet build (Join-Path $Workspace 'engine\openra\OpenRA.Mods.Common\OpenRA.Mods.Common.csproj') --no-restore "-p:OutDir=$BuildOutput\"
    }
    if ($FullMissions) {
        Invoke-Gate 'full-mission-corpus' {
            & $Python -m openra_ai_companion.cli mission-eval --max-ticks $MissionMaxTicks
        }
    }
}
finally {
    $report = [ordered]@{
        generated_at = [DateTimeOffset]::UtcNow.ToString('o')
        started_at = $StartedAt.ToString('o')
        passed = $Gates.Count -gt 0 -and @($Gates | Where-Object { -not $_.passed }).Count -eq 0
        full_missions = [bool]$FullMissions
        gates = $Gates
    }
    New-Item -ItemType Directory -Force -Path (Split-Path -Parent $ReportPath) | Out-Null
    $report | ConvertTo-Json -Depth 8 | Set-Content -Encoding UTF8 $ReportPath
    Write-Host "Quality-gate report: $ReportPath"
}
