@echo off
chcp 65001 >nul
setlocal
cd /d "%~dp0"

rem Original React version (source src/App.tsx) on a separate port 8084
set "REACT_PORT=8084"
set "VITE_BIN=node_modules\vite\bin\vite.js"

echo Starting original React version at http://localhost:%REACT_PORT%
echo Source: src\App.tsx (page reloads automatically on save)
echo Keep this window open while browsing the site.
echo.

rem Install dependencies only if vite is missing
if not exist "%VITE_BIN%" (
  echo [i] vite not found in node_modules, installing dependencies...
  call npm install
)
if not exist "%VITE_BIN%" (
  echo [x] Could not find vite. Check Node.js and project dependencies.
  pause
  exit /b 1
)

rem Open the browser a few seconds later, once Vite is up
start "" cmd /c "timeout /t 4 /nobreak >nul & start "" http://localhost:%REACT_PORT%"

set "PORT=%REACT_PORT%"
node "%VITE_BIN%" --port %REACT_PORT% --strictPort %*
set "EXIT_CODE=%ERRORLEVEL%"

echo.
echo Dev server stopped (exit code %EXIT_CODE%).
pause
exit /b %EXIT_CODE%
