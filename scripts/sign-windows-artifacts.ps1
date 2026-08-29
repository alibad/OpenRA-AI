[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)]
    [string[]]$Paths,
    [switch]$RequireSignatures,
    [switch]$VerifyOnly
)

$ErrorActionPreference = "Stop"
$signaturesRequired = $RequireSignatures -or $env:OPENRA_AI_OFFICIAL_RELEASE -eq "1"
$timestampUrl = if ($env:WINDOWS_SIGNING_TIMESTAMP_URL) {
    $env:WINDOWS_SIGNING_TIMESTAMP_URL
} else {
    "https://timestamp.digicert.com"
}

if (-not [Uri]::IsWellFormedUriString($timestampUrl, [UriKind]::Absolute) -or
    ([Uri]$timestampUrl).Scheme -ne "https") {
    throw "WINDOWS_SIGNING_TIMESTAMP_URL must be an absolute HTTPS URL."
}

function Resolve-SignTool {
    if ($env:WINDOWS_SIGNTOOL_PATH) {
        if (-not (Test-Path -LiteralPath $env:WINDOWS_SIGNTOOL_PATH -PathType Leaf)) {
            throw "WINDOWS_SIGNTOOL_PATH does not point to signtool.exe."
        }
        return (Resolve-Path -LiteralPath $env:WINDOWS_SIGNTOOL_PATH).Path
    }

    $command = Get-Command signtool.exe -ErrorAction SilentlyContinue
    if ($command) {
        return $command.Source
    }

    $kitsRoot = ${env:ProgramFiles(x86)}
    if ($kitsRoot) {
        $candidates = @(Get-ChildItem -Path (Join-Path $kitsRoot "Windows Kits\10\bin\*\x64\signtool.exe") `
            -File -ErrorAction SilentlyContinue | Sort-Object FullName -Descending)
        if ($candidates.Count -gt 0) {
            return $candidates[0].FullName
        }
    }

    throw "signtool.exe is required. Install the Windows 10/11 SDK or set WINDOWS_SIGNTOOL_PATH."
}

function Assert-AuthenticodeSignature {
    param([string]$Path, [string]$SignTool)

    $signature = Get-AuthenticodeSignature -LiteralPath $Path
    if ($signature.Status -ne [System.Management.Automation.SignatureStatus]::Valid) {
        throw "Authenticode verification failed for $Path ($($signature.Status): $($signature.StatusMessage))."
    }
    if (-not $signature.TimeStamperCertificate) {
        throw "Authenticode signature is missing its trusted timestamp: $Path"
    }

    & $SignTool verify /pa /all /v $Path | Out-Host
    if ($LASTEXITCODE -ne 0) {
        throw "signtool verification failed for $Path."
    }
}

$resolvedPaths = @($Paths | ForEach-Object {
    if (-not (Test-Path -LiteralPath $_ -PathType Leaf)) {
        throw "Windows signing input is missing: $_"
    }
    (Resolve-Path -LiteralPath $_).Path
})

if ($resolvedPaths.Count -eq 0) {
    throw "At least one Windows executable must be supplied for signing or verification."
}

$signTool = $null
if ($VerifyOnly -or $signaturesRequired -or $env:WINDOWS_SIGNING_CERTIFICATE_THUMBPRINT) {
    $signTool = Resolve-SignTool
}

if ($VerifyOnly) {
    foreach ($path in $resolvedPaths) {
        Assert-AuthenticodeSignature -Path $path -SignTool $signTool
    }
    return
}

$thumbprint = ([string]$env:WINDOWS_SIGNING_CERTIFICATE_THUMBPRINT -replace '\s', '').ToUpperInvariant()
if (-not $thumbprint) {
    if ($signaturesRequired) {
        throw "Official Windows releases require WINDOWS_SIGNING_CERTIFICATE_THUMBPRINT for a code-signing certificate with an accessible private key."
    }
    Write-Warning "Windows signing is not configured; development artifacts will remain unsigned."
    return
}
if ($thumbprint -notmatch '^[A-F0-9]{40}$') {
    throw "WINDOWS_SIGNING_CERTIFICATE_THUMBPRINT must be a 40-character SHA-1 certificate thumbprint."
}

$store = if ($env:WINDOWS_SIGNING_CERTIFICATE_STORE) {
    $env:WINDOWS_SIGNING_CERTIFICATE_STORE
} else {
    "CurrentUser"
}
if ($store -notin @("CurrentUser", "LocalMachine")) {
    throw "WINDOWS_SIGNING_CERTIFICATE_STORE must be CurrentUser or LocalMachine."
}

$certificate = Get-Item -LiteralPath "Cert:\$store\My\$thumbprint" -ErrorAction SilentlyContinue
if (-not $certificate -or -not $certificate.HasPrivateKey) {
    throw "The configured Windows code-signing certificate is missing from Cert:\$store\My or has no accessible private key."
}

foreach ($path in $resolvedPaths) {
    $arguments = @("sign", "/sha1", $thumbprint, "/fd", "SHA256", "/tr", $timestampUrl, "/td", "SHA256", "/v")
    if ($store -eq "LocalMachine") {
        $arguments += "/sm"
    }
    $arguments += $path

    & $signTool @arguments | Out-Host
    if ($LASTEXITCODE -ne 0) {
        throw "signtool failed to sign $path."
    }
    Assert-AuthenticodeSignature -Path $path -SignTool $signTool
}
