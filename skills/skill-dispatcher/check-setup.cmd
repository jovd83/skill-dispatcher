@echo off
setlocal
echo Skill Dispatcher Diagnostics
echo ============================
echo.

echo [1] Checking Python environment...
py --version >nul 2>nul
if %ERRORLEVEL% EQU 0 (
    echo [OK] Python Launcher found.
    py --version
) else (
    echo [WARN] Python Launcher NOT found.
)

python --version >nul 2>nul
if %ERRORLEVEL% EQU 0 (
    echo [OK] Python command found.
    python --version
    
    python -c "import sys; print('STORE' if 'WindowsApps' in sys.executable else 'OK')" > .tmp_check
    set /p CHECK_RESULT=<.tmp_check
    del .tmp_check
    
    if "%CHECK_RESULT%"=="STORE" (
        echo [FAIL] Python is pointing to the Microsoft Store stub!
        echo        This will cause execution issues. 
        echo        Please disable App execution aliases for Python in Windows Settings.
    ) else (
        echo [OK] Python is a real executable.
    )
) else (
    echo [FAIL] Python command NOT found in PATH.
)

echo.
echo [2] Checking Project Structure...
if exist "scripts\dispatch_logger.py" (
    echo [OK] dispatch_logger.py found.
) else (
    echo [FAIL] dispatch_logger.py NOT found. Are you in the skill-dispatcher directory?
)

echo.
echo [3] Checking Config...
if exist "config\settings.json" (
    echo [OK] settings.json found.
) else (
    echo [WARN] settings.json NOT found.
)

echo.
echo Done.
endlocal
