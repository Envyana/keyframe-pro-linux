@echo off
REM Keyframe Pro Linux — Windows launcher.
REM Activates the venv if present, then launches the app.

setlocal
cd /d "%~dp0"

if exist ".venv\Scripts\python.exe" (
    set "PY=.\.venv\Scripts\python.exe"
) else (
    set "PY=python"
)

set "PYTHONPATH=%CD%\src;%PYTHONPATH%"
"%PY%" -m keyframe_pro %*
