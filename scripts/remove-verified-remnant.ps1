param([Parameter(Mandatory=$true)][string]$Target,[Parameter(Mandatory=$true)][string]$WorkspaceRoot)
$ErrorActionPreference='Stop'
$resolved=[IO.Path]::GetFullPath($Target)
$root=[IO.Path]::GetFullPath($WorkspaceRoot)
if ([IO.Path]::GetDirectoryName($resolved) -ne $root -or [IO.Path]::GetFileName($resolved) -notlike '*-wt-*') {throw 'Unsafe remnant path'}
if ((Get-Item -LiteralPath $resolved -Force).Attributes -band [IO.FileAttributes]::ReparsePoint) {throw 'Root must not be a link'}
Remove-Item -LiteralPath $resolved -Recurse -Force
