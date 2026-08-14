[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)]
    [string]$Url,
    [Parameter(Mandatory = $true)]
    [ValidatePattern('^[0-9a-fA-F]{64}$')]
    [string]$SHA256,
    [Parameter(Mandatory = $true)]
    [string]$Destination
)

$ErrorActionPreference = "Stop"
$destinationPath = [IO.Path]::GetFullPath($Destination)
$parent = Split-Path -Parent $destinationPath
if (-not (Test-Path -LiteralPath $parent)) {
    New-Item -ItemType Directory -Path $parent -Force | Out-Null
}

$temporary = Join-Path ([IO.Path]::GetTempPath()) ("openra-ai-pack-" + [guid]::NewGuid().ToString("N") + ".zip")
try {
    $ProgressPreference = "SilentlyContinue"
    Invoke-WebRequest -Uri $Url -OutFile $temporary -UseBasicParsing
    $actual = (Get-FileHash -LiteralPath $temporary -Algorithm SHA256).Hash.ToLowerInvariant()
    if ($actual -ne $SHA256.ToLowerInvariant()) {
        throw "AI pack checksum mismatch. Expected $SHA256, received $actual."
    }

    if (Test-Path -LiteralPath $destinationPath) {
        $resolved = (Resolve-Path -LiteralPath $destinationPath).Path
        $resolvedParent = (Resolve-Path -LiteralPath $parent).Path
        if (-not $resolved.StartsWith($resolvedParent + [IO.Path]::DirectorySeparatorChar)) {
            throw "Refusing to replace an AI directory outside the selected installation."
        }
        Remove-Item -LiteralPath $resolved -Recurse -Force
    }
    New-Item -ItemType Directory -Path $destinationPath -Force | Out-Null
    Expand-Archive -LiteralPath $temporary -DestinationPath $destinationPath -Force
}
finally {
    Remove-Item -LiteralPath $temporary -Force -ErrorAction SilentlyContinue
}

Write-Host "Local AI pack installed to $destinationPath"
