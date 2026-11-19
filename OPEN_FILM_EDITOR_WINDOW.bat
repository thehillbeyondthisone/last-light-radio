@echo off
rem Opens the Film editor in its own app window (no tabs or address bar).
rem Starts the film service first (same as OPEN_FILM_EDITOR.bat) if it is not already running on port 8769.
cd /d "%~dp0"
set "URL=http://127.0.0.1:8769/"

curl.exe -s -o nul --max-time 2 "%URL%"
if errorlevel 1 (
  echo Starting the film service in its own window...
  start "Last Light Radio film service" cmd /c "%~dp0OPEN_FILM_EDITOR.bat"
  for /l %%i in (1,1,30) do (
    timeout /t 1 /nobreak >nul
    curl.exe -s -o nul --max-time 2 "%URL%" && goto ready
  )
  echo The film service did not answer on %URL% after 30 seconds. Check its window for errors.
  pause
  exit /b 1
)
:ready

set "BROWSER="
for %%P in ("%ProgramFiles%\Google\Chrome\Application\chrome.exe" "%ProgramFiles(x86)%\Google\Chrome\Application\chrome.exe" "%LocalAppData%\Google\Chrome\Application\chrome.exe" "%ProgramFiles(x86)%\Microsoft\Edge\Application\msedge.exe" "%ProgramFiles%\Microsoft\Edge\Application\msedge.exe") do (
  if not defined BROWSER if exist %%P set "BROWSER=%%~P"
)
if not defined BROWSER (
  echo Chrome or Edge not found; opening in the default browser instead.
  start "" "%URL%"
  exit /b 0
)
start "" "%BROWSER%" --app="%URL%" --window-size=1600,1000
