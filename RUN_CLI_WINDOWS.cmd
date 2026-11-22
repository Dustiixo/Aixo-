@echo off
setlocal
cd /d "%~dp0"
set "AIXO_WALL_HOME=%LOCALAPPDATA%\OXsukra\AIXO_Local_Bridge_M0_2"
where py >nul 2>&1
if not errorlevel 1 (
  py -3 cli.py %*
) else (
  python cli.py %*
)
endlocal
