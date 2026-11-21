@echo off
setlocal
cd /d "%~dp0"
py -3 --version >nul 2>nul
if errorlevel 1 (
    python --version >nul 2>nul
    if errorlevel 1 (
        echo Installer Python 3.10 ou plus recent pour lancer cette application
        pause
        exit /b 1
    )
    python -B "%~dp0python\server.py" %*
) else (
    py -3 -B "%~dp0python\server.py" %*
)
if errorlevel 1 (
    echo Le lancement a echoue. Le message ci-dessus indique la cause
    pause
    exit /b 1
)
