@echo off
rem One-command launcher for the archival cursive transcriber (Windows).
rem
rem   run letter.jpg                     transcribe one scan (Claude engine)
rem   run scans\ -o transcripts\         transcribe a whole folder
rem   run letter.jpg --engine local      no-API-key mode (local model)
rem
rem The first run sets everything up automatically: it creates a private
rem Python environment in .venv\, installs the dependencies, and (for the
rem Claude engine) asks once for your API key and remembers it in .env.

setlocal enabledelayedexpansion
cd /d "%~dp0"

rem --- find Python -------------------------------------------------------------
set "PY=python"
%PY% --version >nul 2>nul
if errorlevel 1 (
    set "PY=py"
    %PY% --version >nul 2>nul
    if errorlevel 1 (
        echo error: Python 3 is not installed. Get it from https://www.python.org/downloads/
        echo During installation, tick "Add Python to PATH".
        exit /b 1
    )
)

rem --- one-time environment setup ----------------------------------------------
if not exist .venv (
    echo First run: creating a private Python environment ^(one time only^)...
    %PY% -m venv .venv || exit /b 1
)
call .venv\Scripts\activate.bat

python -c "import anthropic" >nul 2>nul
if errorlevel 1 (
    echo Installing dependencies ^(one time only^)...
    pip install --quiet -r requirements.txt || exit /b 1
)

rem --- no arguments: show examples and stop --------------------------------------
if "%~1"=="" (
    echo Setup is done. Now tell it what to transcribe:
    echo.
    echo   run letter.jpg                     one scan
    echo   run scans\ -o transcripts\         a whole folder
    echo   run letter.jpg --engine local      without an API key
    echo   run --help                         all options
    exit /b 0
)

rem --- inspect arguments ----------------------------------------------------------
set "USE_LOCAL=0"
echo %* | findstr /c:"--engine local" >nul 2>nul && set "USE_LOCAL=1"
echo %* | findstr /c:"--engine=local" >nul 2>nul && set "USE_LOCAL=1"
set "WANTS_HELP=0"
echo %* | findstr /c:"--help" >nul 2>nul && set "WANTS_HELP=1"
echo %* | findstr /r /c:"\<-h\>" >nul 2>nul && set "WANTS_HELP=1"

if "%USE_LOCAL%"=="1" (
    python -c "import torch, transformers" >nul 2>nul
    if errorlevel 1 (
        echo Installing local-engine dependencies ^(one time only, ~1-2 GB^)...
        pip install --quiet -r requirements-local.txt || exit /b 1
    )
)

rem --- API key (Claude engine only; not needed for --help) ------------------------
if "%USE_LOCAL%"=="1" goto :run
if "%WANTS_HELP%"=="1" goto :run
if defined ANTHROPIC_API_KEY goto :run

if exist .env (
    for /f "usebackq tokens=1,* delims==" %%a in (".env") do (
        if "%%a"=="ANTHROPIC_API_KEY" set "ANTHROPIC_API_KEY=%%b"
    )
)
if defined ANTHROPIC_API_KEY goto :run

echo.
echo The Claude engine needs an Anthropic API key ^(create one at
echo https://console.anthropic.com/ under "API Keys"^).
echo It will be remembered in the local .env file for next time.
echo Tip: to skip API keys entirely, use:  run ^<file^> --engine local
echo.
set /p ANTHROPIC_API_KEY=Paste your API key (sk-ant-...):
if not defined ANTHROPIC_API_KEY (
    echo error: no key entered.
    exit /b 1
)
>.env echo ANTHROPIC_API_KEY=%ANTHROPIC_API_KEY%
echo Saved to .env (kept out of git).

:run
python -m transcriber %*
