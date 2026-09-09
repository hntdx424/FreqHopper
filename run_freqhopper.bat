@echo off
setlocal
cd /d "%~dp0"

if exist ".venv\Scripts\python.exe" (
    ".venv\Scripts\python.exe" -m freqhopper %*
) else (
    python -m freqhopper %*
)

if errorlevel 1 (
    echo.
    echo FreqHopper exited with an error. See the message above.
    pause
)
endlocal
