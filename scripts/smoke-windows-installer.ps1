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
$stateBackupRoot = Join-Path $artifactResolved ("installer-smoke-state-" + [guid]::NewGuid().ToString("N"))
$desktopRoot = [Environment]::GetFolderPath([Environment+SpecialFolder]::DesktopDirectory)
$programsRoot = [Environment]::GetFolderPath([Environment+SpecialFolder]::Programs)
$desktopShortcut = Join-Path $desktopRoot "OpenRA AI.lnk"
$startMenuFolder = Join-Path $programsRoot "OpenRA AI"
$startMenuShortcut = Join-Path $startMenuFolder "OpenRA AI.lnk"
$uninstallRegistryKey = "HKCU\Software\Microsoft\Windows\CurrentVersion\Uninstall\OpenRA AI"
$uninstallRegistryPath = "Registry::HKEY_CURRENT_USER\Software\Microsoft\Windows\CurrentVersion\Uninstall\OpenRA AI"
$desktopShortcutBackup = Join-Path $stateBackupRoot "Desktop\OpenRA AI.lnk"
$startMenuBackup = Join-Path $stateBackupRoot "StartMenu\OpenRA AI"
$registryBackup = Join-Path $stateBackupRoot "uninstall.reg"

if ([string]::IsNullOrWhiteSpace($desktopRoot) -or [string]::IsNullOrWhiteSpace($programsRoot)) {
    throw "Unable to resolve the current user's Desktop or Start Menu folder."
}

$programsFull = [IO.Path]::GetFullPath($programsRoot).TrimEnd([IO.Path]::DirectorySeparatorChar)
$startMenuFull = [IO.Path]::GetFullPath($startMenuFolder)
if (-not $startMenuFull.StartsWith($programsFull + [IO.Path]::DirectorySeparatorChar, [StringComparison]::OrdinalIgnoreCase)) {
    throw "Refusing to manage a smoke-test Start Menu folder outside the current user's Programs folder."
}

$hadDesktopShortcut = Test-Path -LiteralPath $desktopShortcut -PathType Leaf
$hadStartMenuFolder = Test-Path -LiteralPath $startMenuFolder -PathType Container
New-Item -ItemType Directory -Path $stateBackupRoot | Out-Null
if ($hadDesktopShortcut) {
    New-Item -ItemType Directory -Path (Split-Path -Parent $desktopShortcutBackup) | Out-Null
    Copy-Item -LiteralPath $desktopShortcut -Destination $desktopShortcutBackup
}
if ($hadStartMenuFolder) {
    New-Item -ItemType Directory -Path (Split-Path -Parent $startMenuBackup) | Out-Null
    Copy-Item -LiteralPath $startMenuFolder -Destination $startMenuBackup -Recurse
}

$hadUninstallRegistryKey = Test-Path -LiteralPath $uninstallRegistryPath
if ($hadUninstallRegistryKey) {
    & reg.exe export $uninstallRegistryKey $registryBackup /y | Out-Null
    if ($LASTEXITCODE -ne 0 -or -not (Test-Path -LiteralPath $registryBackup -PathType Leaf)) {
        throw "Unable to back up the existing OpenRA AI uninstall registration."
    }
}

New-Item -ItemType Directory -Path $testRoot | Out-Null

try {
    $install = Start-Process -FilePath $installer -ArgumentList "/S", "/D=$testRoot" -Wait -PassThru
    if ($install.ExitCode -ne 0) {
        throw "The silent installer exited with code $($install.ExitCode)."
    }

    foreach ($required in @(
        (Join-Path $testRoot "Play-OpenRAAI.cmd"),
        (Join-Path $testRoot "bin\openra-ai-companion.exe"),
        (Join-Path $testRoot "bin\openra-ai-runtime.exe"),
        (Join-Path $testRoot "engine\openra\bin\OpenRA-AI.exe"),
        (Join-Path $testRoot "assets\brand\rtsai.ico"),
        (Join-Path $testRoot "Uninstall OpenRA AI.exe")
    )) {
        if (-not (Test-Path -LiteralPath $required)) {
            throw "Installed package is missing: $required"
        }
    }

    foreach ($requiredShortcut in @($desktopShortcut, $startMenuShortcut)) {
        if (-not (Test-Path -LiteralPath $requiredShortcut -PathType Leaf)) {
            throw "Installed package did not create the expected shortcut: $requiredShortcut"
        }
    }

    $shell = New-Object -ComObject WScript.Shell
    $expectedShortcutTarget = Join-Path $testRoot "Play-OpenRAAI.cmd"
    $expectedShortcutIcon = (Join-Path $testRoot "assets\brand\rtsai.ico") + ",0"
    foreach ($shortcutPath in @($desktopShortcut, $startMenuShortcut)) {
        $shortcut = $shell.CreateShortcut($shortcutPath)
        if ($shortcut.TargetPath -ne $expectedShortcutTarget) {
            throw "Installed shortcut targets the wrong launcher: $shortcutPath"
        }
        if ($shortcut.IconLocation -ne $expectedShortcutIcon) {
            throw "Installed shortcut does not use the OpenRA AI icon: $shortcutPath"
        }
    }

    $uninstaller = Join-Path $testRoot "Uninstall OpenRA AI.exe"
    $uninstall = Start-Process -FilePath $uninstaller -ArgumentList "/S", "_?=$testRoot" -Wait -PassThru
    if ($uninstall.ExitCode -ne 0) {
        throw "The silent uninstaller exited with code $($uninstall.ExitCode)."
    }
}
finally {
    try {
        if (Test-Path -LiteralPath $desktopShortcut) {
            Remove-Item -LiteralPath $desktopShortcut -Force
        }
        if ($hadDesktopShortcut) {
            Copy-Item -LiteralPath $desktopShortcutBackup -Destination $desktopShortcut
        }

        if (Test-Path -LiteralPath $startMenuFolder) {
            Remove-Item -LiteralPath $startMenuFolder -Recurse -Force
        }
        if ($hadStartMenuFolder) {
            Copy-Item -LiteralPath $startMenuBackup -Destination $startMenuFolder -Recurse
        }

        if (Test-Path -LiteralPath $uninstallRegistryPath) {
            & reg.exe delete $uninstallRegistryKey /f | Out-Null
            if ($LASTEXITCODE -ne 0) {
                throw "Unable to clear the smoke-test OpenRA AI uninstall registration."
            }
        }
        if ($hadUninstallRegistryKey) {
            & reg.exe import $registryBackup | Out-Null
            if ($LASTEXITCODE -ne 0) {
                throw "Unable to restore the existing OpenRA AI uninstall registration."
            }
        }
    }
    finally {
        foreach ($temporaryRoot in @($testRoot, $stateBackupRoot)) {
            if (-not (Test-Path -LiteralPath $temporaryRoot)) {
                continue
            }

            $temporaryResolved = (Resolve-Path -LiteralPath $temporaryRoot).Path
            if (-not $temporaryResolved.StartsWith($artifactResolved + [IO.Path]::DirectorySeparatorChar)) {
                throw "Refusing to remove an installer smoke-test directory outside artifacts."
            }
            Remove-Item -LiteralPath $temporaryResolved -Recurse -Force
        }
    }
}

Write-Host "Windows setup installer smoke test passed." -ForegroundColor Green
