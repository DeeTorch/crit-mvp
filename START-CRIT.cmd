@echo off
setlocal enabledelayedexpansion
title CRIT Quick Start & Installer

:: ── COLOR SETUP ──────────────────────────────────────────────────────────────
set "ESC="
set "GREEN=%ESC%[92m"
set "YELLOW=%ESC%[93m"
set "RED=%ESC%[91m"
set "CYAN=%ESC%[96m"
set "RESET=%ESC%[0m"

echo %CYAN%============================================================%RESET%
echo %CYAN%   🚀 CRIT: Code Review ^& Intelligence Tool Quick Start    %RESET%
echo %CYAN%============================================================%RESET%

:: ── [1/4] PYTHON CHECK ──────────────────────────────────────────────────────
echo %YELLOW%[1/4] Checking Python Environment...%RESET%
python --version >nul 2>&1
if %errorlevel% neq 0 (
    echo %RED%[ERROR] Python not found. Please install Python 3.10+ from python.org%RESET%
    pause
    exit /b 1
)

if not exist venv (
    echo    Creating virtual environment...
    python -m venv venv
)

:: ── [2/4] INSTALLATION ──────────────────────────────────────────────────────
echo %YELLOW%[2/4] Syncing Dependencies...%RESET%
venv\Scripts\python -m pip install -q --upgrade pip
venv\Scripts\python -m pip install -q -r requirements.txt
if %errorlevel% neq 0 (
    echo %RED%[ERROR] Dependency installation failed.%RESET%
    pause
    exit /b 1
)
echo    %GREEN%Dependencies synced successfully.%RESET%

:: ── [3/4] DIAGNOSTICS ──────────────────────────────────────────────────────
echo %YELLOW%[3/4] Running Security Diagnostics...%RESET%
if not exist .env (
    echo    %RED%[MISSING] .env file not found.%RESET%
    set /p key="    Please enter your GEMINI_API_KEY: "
    echo GEMINI_API_KEY=!key! > .env
    echo    %GREEN%[.env] Created and key saved.%RESET%
) else (
    findstr /C:"GEMINI_API_KEY" .env >nul
    if !errorlevel! neq 0 (
        echo    %RED%[INVALID] .env exists but GEMINI_API_KEY is missing.%RESET%
        set /p key="    Please enter your GEMINI_API_KEY: "
        echo GEMINI_API_KEY=!key! >> .env
    ) else (
        echo    %GREEN%[OK] API Key detected.%RESET%
    )
)

:: ── [4/4] SHORTCUT SETUP ────────────────────────────────────────────────────
echo %YELLOW%[4/4] Setting up Desktop Shortcut...%RESET%
set "SHORTCUT_PATH=%USERPROFILE%\Desktop\CRIT Dashboard.lnk"
set "ICON_PATH=%~dp0venv\Scripts\python.exe"
powershell -Command "$s=(New-Object -ComObject WScript.Shell).CreateShortcut('%SHORTCUT_PATH%');$s.TargetPath='cmd.exe';$s.Arguments='/c \"cd /d %~dp0 && START-CRIT.cmd\"';$s.IconLocation='%ICON_PATH%';$s.Save()"
echo    %GREEN%[CREATED] 'CRIT Dashboard' shortcut added to Desktop.%RESET%

:: ── INTERACTIVE LAUNCHER ────────────────────────────────────────────────────
echo.
echo %GREEN%✨ CRIT is ready to go!%RESET%
echo.
echo 1. 🖥️  Launch Visual Dashboard (Streamlit)
echo 2. 📟  Launch Terminal UI (Textual)
echo 3. 🛡️  Run CLI Audit (Self-Audit)
echo 4. ❌  Exit
echo.

set /p choice="Select an option (1-4): "

if "%choice%"=="1" (
    echo %CYAN%🚀 Launching Streamlit Dashboard...%RESET%
    venv\Scripts\streamlit run app.py
) else if "%choice%"=="2" (
    echo %CYAN%🚀 Launching Textual TUI...%RESET%
    venv\Scripts\python tui.py
) else if "%choice%"=="3" (
    echo %CYAN%🚀 Running CLI Audit on self...%RESET%
    venv\Scripts\python crit_orchestrator.py --target crit_orchestrator.py
    pause
) else (
    echo %YELLOW%Setup complete. Use the desktop shortcut to launch anytime!%RESET%
    timeout /t 3
)
