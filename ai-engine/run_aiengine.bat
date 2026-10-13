@echo off
title LUMA AiEngine [Port 8000]
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" (
    echo [ERROR] Virtual environment not found at .venv!
    pause
    exit /b 1
)
echo ========================================================
echo   LUMA AiEngine - Live Console
echo   Listening on: http://0.0.0.0:8000
echo   Provider: WebUI Forge (http://127.0.0.1:7860)
echo ========================================================
echo.
.venv\Scripts\python.exe app.py
pause
