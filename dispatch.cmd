@echo off
setlocal
set SCRIPT_DIR=%~dp0
set PYTHON_SCRIPT=%SCRIPT_DIR%scripts\dispatch_cli.py

:: 1. Try Python Launcher (most reliable on Windows)
py --version >nul 2>nul
if %ERRORLEVEL% EQU 0 (
    py "%PYTHON_SCRIPT%" %*
    goto :EOF
)

:: 2. Try 'python'
python --version >nul 2>nul
if %ERRORLEVEL% EQU 0 (
    python "%PYTHON_SCRIPT%" %*
    goto :EOF
)

:: 3. Try 'python3'
python3 --version >nul 2>nul
if %ERRORLEVEL% EQU 0 (
    python3 "%PYTHON_SCRIPT%" %*
    goto :EOF
)

echo [ERROR] Python could not be found or executed.
echo Please ensure Python is installed and added to your PATH.
exit /b 1
