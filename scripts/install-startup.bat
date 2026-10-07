@echo off
setlocal
cd /d "%~dp0.."
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0install-startup.ps1"
if errorlevel 1 (
  echo.
  echo Startup configuration failed. Review the error above.
  pause
)
