@echo off
setlocal EnableExtensions
cd /d "%~dp0"
title AIXO Local Bridge M0.2 + RC1 regression - G0 tests
set "PYTHONHOME="
set "PYTHONPATH="
set "AIXO_PY_EXE="
where py >nul 2>&1
if not errorlevel 1 for /f "delims=" %%P in ('py -3 -c "import sys;print(sys.executable)" 2^>nul') do set "AIXO_PY_EXE=%%P"
if not defined AIXO_PY_EXE (
  where python >nul 2>&1
  if not errorlevel 1 (
    for /f "delims=" %%P in ('python -c "import sys;print(sys.executable)" 2^>nul') do set "AIXO_PY_EXE=%%P"
  )
)
if not defined AIXO_PY_EXE (
 echo [G0 FAILED] Python was not found.
 pause
 exit /b 2
)
"%AIXO_PY_EXE%" -m unittest discover -s tests -v
if errorlevel 1 (
 echo.
 echo [G0 FAILED] This release must NOT be promoted.
 pause
 exit /b 1
)
echo.
echo [G0 LOCAL TESTS PASS] Native Windows GUI acceptance is STILL a separate gate.
pause
endlocal
exit /b 0
