@echo off
setlocal EnableExtensions
cd /d "%~dp0"
title AIXO Local Bridge M0.2 - ISOLATED SAFE DEMO
set "PYTHONHOME="
set "PYTHONPATH="
where py >nul 2>&1
if not errorlevel 1 (
 py -3 demo_bridge.py
) else (
 python demo_bridge.py
)
if errorlevel 1 (
 echo.
 echo [G0 FAILED] Demo did not pass. Copy this text.
 pause
 exit /b 2
)
echo.
echo [DEMO PASS] Only synthetic isolated stores were modified. See results directory above.
pause
exit /b 0
