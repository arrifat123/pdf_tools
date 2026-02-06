@echo off
title PDF PAGE ROTATOR
echo.
echo   ========================================
echo        PDF  PAGE  ROTATOR
echo   ========================================
echo.

if "%~1"=="" (
    echo   [!] ERROR: No file was provided.
    echo.
    echo   HOW TO USE:
    echo   Drag and drop a PDF file onto this
    echo   batch file to rotate its pages.
    echo.
    pause
    exit /b 1
)

python "%~dp0rotator.py" "%~1"

echo.
pause
