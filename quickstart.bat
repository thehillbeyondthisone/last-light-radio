@echo off
setlocal
title Last Light Radio
powershell.exe -NoLogo -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\run.ps1" quickstart %*
set "LLR_EXIT=%ERRORLEVEL%"
if not "%LLR_EXIT%"=="0" (
    echo.
    echo Last Light Radio could not start. See the error above.
    pause
)
exit /b %LLR_EXIT%
