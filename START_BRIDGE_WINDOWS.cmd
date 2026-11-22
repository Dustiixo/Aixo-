@echo off
setlocal EnableExtensions
cd /d "%~dp0"
set "AIXO_BRIDGE_HOME=%LOCALAPPDATA%\OXsukra\AIXO_Local_Bridge_M0_2"
set "AIXO_WALL_HOME=%LOCALAPPDATA%\OXsukra\AIXO_Local_Bridge_M0_2"
title AIXO Local Bridge M0.2 - Native Windows / OFFLINE
set "PYTHONHOME="
set "PYTHONPATH="
set "AIXO_PY_EXE="
where py >nul 2>&1
if not errorlevel 1 for /f "delims=" %%P in ('py -3 -c "import sys;print(sys.executable)" 2^>nul') do set "AIXO_PY_EXE=%%P"
if not defined AIXO_PY_EXE (
 where python >nul 2>&1
 if not errorlevel 1 for /f "delims=" %%P in ('python -c "import sys;print(sys.executable)" 2^>nul') do set "AIXO_PY_EXE=%%P"
)
if not defined AIXO_PY_EXE (
 echo [G0 BLOCKED] Python 3.10 or newer not found.
 pause
 exit /b 2
)
"%AIXO_PY_EXE%" -c "import sys,sqlite3,json;assert sys.version_info >= (3,10); print('G0 Python:',sys.version.split()[0])"
if errorlevel 1 (
 echo [G0 BLOCKED] Python backend unusable.
 pause
 exit /b 2
)
where powershell.exe >nul 2>&1
if errorlevel 1 (
 echo [G0 BLOCKED] Windows PowerShell 5.1 missing.
 pause
 exit /b 2
)
powershell.exe -NoProfile -ExecutionPolicy Bypass -STA -File "%~dp0BRIDGE_WINDOWS.ps1"
if errorlevel 1 (
 echo [G0 BLOCKED] Bridge GUI failed. Copy this output for diagnosis.
 pause
 exit /b 1
)
endlocal
exit /b 0
