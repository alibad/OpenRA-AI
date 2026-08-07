@echo off
setlocal
set "OPENRA_AI_ROOT=%~dp0"
set "OPENRA_AI_MAP=%~1"
if "%OPENRA_AI_MAP%"=="" set "OPENRA_AI_MAP=%OPENRA_AI_ROOT%generated\missions\riyadh-crossing-42.oramap"
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%OPENRA_AI_ROOT%apps\launcher\Start-OpenRAAI.ps1" -Map "%OPENRA_AI_MAP%"
set "OPENRA_AI_EXIT=%ERRORLEVEL%"
if not "%OPENRA_AI_EXIT%"=="0" pause
endlocal & exit /b %OPENRA_AI_EXIT%
