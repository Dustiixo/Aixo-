@echo off
setlocal EnableExtensions
cd /d "%~dp0"
set "AIXO_BRIDGE_HOME=%LOCALAPPDATA%\OXsukra\AIXO_Local_Bridge_M0_2"
set "AIXO_WALL_HOME=%LOCALAPPDATA%\OXsukra\AIXO_Local_Bridge_M0_2"
set "PYTHONHOME="
set "PYTHONPATH="
where py >nul 2>&1
if not errorlevel 1 (
 py -3 bridge_cli.py %*
) else (
 python bridge_cli.py %*
)
exit /b %ERRORLEVEL%
