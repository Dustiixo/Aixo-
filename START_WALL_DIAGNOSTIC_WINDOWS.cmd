@echo off
setlocal EnableExtensions
cd /d "%~dp0"
title AIXO Collision Wall RC1 - Native Windows (NO TKINTER)
REM Process-local cleanup only; does not change user Python settings.
set "PYTHONHOME="
set "PYTHONPATH="
set "AIXO_WALL_HOME=%LOCALAPPDATA%\OXsukra\AIXO_Local_Bridge_M0_2"
set "AIXO_PY_EXE="
where py >nul 2>&1
if not errorlevel 1 (
  for /f "delims=" %%P in ('py -3 -c "import sys; print(sys.executable)" 2^>nul') do set "AIXO_PY_EXE=%%P"
)
if not defined AIXO_PY_EXE (
  where python >nul 2>&1
  if not errorlevel 1 (
    for /f "delims=" %%P in ('python -c "import sys; print(sys.executable)" 2^>nul') do set "AIXO_PY_EXE=%%P"
  )
)
if not defined AIXO_PY_EXE (
  echo [G0 BLOCKED] No usable Python 3 found.
  echo AIXO needs Python 3.10 or newer for its SQLite engine.
  pause
  exit /b 2
)
"%AIXO_PY_EXE%" -c "import sys, sqlite3, json; assert sys.version_info >= (3,10); print('AIXO backend preflight OK:', sys.version.split()[0])"
if errorlevel 1 (
  echo [G0 BLOCKED] Python core backend preflight failed.
  pause
  exit /b 2
)
where powershell.exe >nul 2>&1
if errorlevel 1 (
  echo [G0 BLOCKED] Windows PowerShell 5.1 could not be found.
  pause
  exit /b 2
)
echo AIXO uses native Windows Forms - it does NOT need tkinter or init.tcl.
echo The data store is isolated. Closing the window closes the interface.
powershell.exe -NoProfile -ExecutionPolicy Bypass -STA -File "%~dp0WINDOWS_NATIVE.ps1"
if errorlevel 1 (
  echo.
  echo [G0 BLOCKED] GUI launch failed. Please copy this output.
  pause
  exit /b 1
)
endlocal
exit /b 0
