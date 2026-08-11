@echo off
setlocal
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\play-red-sea-2026.ps1" %*
exit /b %ERRORLEVEL%
