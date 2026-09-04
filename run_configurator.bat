@echo off
cd /d "%~dp0"
poetry run python run_configurator.py
if errorlevel 1 (
    echo.
    echo Startup failed. First run in this project folder:
    echo   poetry install
    echo If Poetry itself is missing:
    echo   python -m pip install poetry
    pause
)
