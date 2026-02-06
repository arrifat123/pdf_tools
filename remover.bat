@echo off
title PDF Watermark Remover — Text Mode
echo.
echo  ============================================================
echo   PDF Watermark Remover — Text Mode
echo   Removes watermark text by keyword matching
echo  ============================================================
echo.

:: Check Python is available
python --version >nul 2>&1
if errorlevel 1 (
    echo  ERROR: Python is not installed or not in PATH.
    echo  Please install Python from https://python.org
    pause
    exit /b 1
)

:: Handle drag-and-drop, command-line argument, or no argument
if "%~1"=="" (
    python "%~dp0remove_watermark.py"
) else (
    python "%~dp0remove_watermark.py" "%~1"
)
pause
