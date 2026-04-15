@echo off
:: Skill Wallboard Generator Wrapper
set SCRIPT_DIR=%~dp0
set PYTHON_SCRIPT=%SCRIPT_DIR%scripts\generate_wallboard.py

:: 1. Try Python Launcher
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

echo [ERROR] Python could not be found.
exit /b 1
