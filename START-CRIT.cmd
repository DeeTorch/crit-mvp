@echo off
title CRIT Quick Start
setlocal enabledelayedexpansion

:: ---------------------------------------------------------------------
:: CONFIGURATION
:: ---------------------------------------------------------------------
set "VENV_DIR=%~dp0venv"
set "REQUIREMENTS=%~dp0requirements.txt"
set "ENV_FILE=%~dp0.env"
set "SHORTCUT_NAME=CRIT Dashboard"

cls
echo ============================================================
echo    CRIT: Code Review ^& Intelligence Tool - Quick Start
echo ============================================================
echo.

:: ---------------------------------------------------------------------
:: PHASE 1: PYTHON ENVIRONMENT CHECK
:: ---------------------------------------------------------------------
echo [1/4] Checking Python Environment...
python --version >nul 2>&1
if %errorlevel% neq 0 (
    echo [ERROR] Python is not installed or not in your system PATH.
    echo Please install Python 3.10+ from https://www.python.org/downloads/
    pause
    exit /b 1
)

:: ---------------------------------------------------------------------
:: PHASE 2: SYNC DEPENDENCIES
:: ---------------------------------------------------------------------
echo [2/4] Syncing Dependencies...
if not exist "%VENV_DIR%" (
    python -m venv venv >nul 2>&1
)

call "%VENV_DIR%\Scripts\activate.bat"

:: Check if requirements need installing
pip show google-genai >nul 2>&1
if %errorlevel% neq 0 (
    pip install -r "%REQUIREMENTS%" >nul 2>&1
    pip install -e . >nul 2>&1
)
echo    [OK] Dependencies synced successfully.

:: ---------------------------------------------------------------------
:: PHASE 3: SECURITY DIAGNOSTICS
:: ---------------------------------------------------------------------
echo [3/4] Running Security Diagnostics...
if not exist "%ENV_FILE%" (
    echo [WARNING] .env file not found.
    echo Creating template .env file...
    (
        echo # CRIT Protocol Configuration
        echo GEMINI_API_KEY=your_actual_api_key_here
    ) > "%ENV_FILE%"
    echo [CRITICAL] Please open '.env' and paste your GEMINI_API_KEY.
    start "" notepad.exe "%ENV_FILE%"
    pause
    exit /b 1
)

:: Quick check for default key
findstr /C:"your_actual_api_key_here" "%ENV_FILE%" >nul
if %errorlevel% equ 0 (
    echo [CRITICAL] Please replace the placeholder API key in '.env'
    start "" notepad.exe "%ENV_FILE%"
    pause
    exit /b 1
)
echo    [OK] API Key detected.

:: ---------------------------------------------------------------------
:: PHASE 4: DESKTOP SHORTCUT SETUP
:: ---------------------------------------------------------------------
echo [4/4] Setting up Desktop Shortcut...
set "SHORTCUT_PATH=%userprofile%\Desktop\%SHORTCUT_NAME%.lnk"

if not exist "%SHORTCUT_PATH%" (
    :: Write a temporary PowerShell script to avoid all CMD-to-PS quoting issues
    set "PS_SCRIPT=%TEMP%\crit_shortcut.ps1"
    > "!PS_SCRIPT!" (
        echo $ws = New-Object -ComObject WScript.Shell
        echo $sc = $ws.CreateShortcut^('%SHORTCUT_PATH%'^)
        echo $sc.TargetPath = '%~f0'
        echo $sc.WorkingDirectory = '%~dp0.'
        echo $sc.Description = 'Launch CRIT Review Dashboard'
        echo $sc.Save^(^)
    )
    powershell -NoProfile -ExecutionPolicy Bypass -File "!PS_SCRIPT!" >nul 2>&1
    del "!PS_SCRIPT!" >nul 2>&1
    echo    [CREATED] 'CRIT Dashboard' shortcut added to Desktop.
) else (
    echo    [OK] Shortcut verified.
)

echo.
echo ============================================================
echo    CRIT is ready to go!
echo ============================================================
echo.

:menu
echo   1.  Launch Visual Dashboard  (Streamlit)
echo   2.  Launch Terminal UI       (Textual)
echo   3.  Run CLI Audit            (Self-Audit)
echo   4.  Exit
echo.
set /p choice="Select an option (1-4): "

if "%choice%"=="1" (
    echo [*] Starting Streamlit dashboard...
    streamlit run app.py
    pause
    goto menu
)
if "%choice%"=="2" (
    echo [*] Launching Textual TUI...
    python crit_orchestrator.py --gui
    pause
    goto menu
)
if "%choice%"=="3" (
    echo [*] Executing git diff audit...
    python crit_orchestrator.py --diff
    pause
    goto menu
)
if "%choice%"=="4" (
    echo Exiting. Goodbye!
    exit /b 0
)

echo Invalid choice. Please select 1 to 4.
timeout /t 2 >nul
goto menu
