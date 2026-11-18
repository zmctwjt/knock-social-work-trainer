@echo off
setlocal
title Knock AI Trainer Launcher
cd /d "%~dp0"

if exist "%~dp0work\pyenv\Scripts\python.exe" goto :havepy
echo [ERROR] Python runtime not found: work\pyenv\Scripts\python.exe
echo         Please run start.bat from the project root folder.
pause
exit /b 2

:havepy
set "PY=%~dp0work\pyenv\Scripts\python.exe"
set "PYTHONIOENCODING=utf-8"
set "PYTHONUTF8=1"
"%PY%" "%~dp0work\run_all.py" %*
set "RC=%ERRORLEVEL%"

if "%RC%"=="0" goto :ok
echo.
echo [FAILED] exit code %RC%, see logs under work\logs\
pause
exit /b %RC%

:ok
echo.
pause
exit /b 0
