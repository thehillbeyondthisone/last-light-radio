@echo off
setlocal
title Last Light Radio Clip Editor
cd /d "%~dp0"
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\run.ps1" clip-editor %*
set "LLR_EXIT=%ERRORLEVEL%"
if not "%LLR_EXIT%"=="0" pause
exit /b %LLR_EXIT%
