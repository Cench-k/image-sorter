@echo off
rem Smart Image Sorter launcher (keep this file ASCII-only: cmd misreads UTF-8 batch files)
chcp 65001 > nul
title Smart Image Sorter
cd /d "%~dp0"

where py >nul 2>nul
if %errorlevel% equ 0 (
    py -3 launcher.py
    goto end
)

where python >nul 2>nul
if %errorlevel% equ 0 (
    python launcher.py
    goto end
)

echo [ERROR] Python not found.
echo Install Python 3.10+ from https://www.python.org/downloads/
echo and check "Add python.exe to PATH" during setup.

:end
pause
