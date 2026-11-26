@echo off
setlocal
chcp 65001 >nul
rem ============================================================
rem  preview.bat - Windows: сборка Figma Make экспорта из source\
rem  и открытие готового сайта в Google Chrome.
rem
rem  ВСЕ артефакты живут ТОЛЬКО внутри source\:
rem    source\node_modules\  - зависимости (рядом с package.json);
rem    source\build\         - собранная статика (index.html, assets);
rem    source\.cache\        - кэш npm/pnpm и служебные скрипты.
rem  source\ можно целиком стереть и заменить другим экспортом -
rem  следующий запуск preview.bat всё установит и соберёт заново.
rem  В корне репозитория артефакты не появляются (они в .gitignore).
rem ============================================================

cd /d "%~dp0"
set "ROOT=%CD%"
set "SRC=%ROOT%\source"
set "PORT=8084"
set "URL=http://localhost:%PORT%/"

rem Кэш npm - строго внутрь source, чтобы npm не писал вне него.
set "npm_config_cache=%SRC%\.cache\npm"

where node >nul 2>&1
if errorlevel 1 goto nonode
where npm >nul 2>&1
if errorlevel 1 goto nonpm
if not exist "%SRC%\package.json" goto nosource

rem ---------- [1/3] зависимости: только source\node_modules ----------
if exist "%SRC%\node_modules\vite\bin\vite.js" goto build
echo [1/3] Устанавливаю зависимости в source\node_modules ...
pushd "%SRC%"
if exist "pnpm-lock.yaml" goto lockpnpm
if exist "package-lock.json" goto locknpmci
call npm install --no-package-lock --no-audit --no-fund
goto installed
:locknpmci
call npm ci --no-audit --no-fund
goto installed
:lockpnpm
where pnpm >nul 2>&1
if errorlevel 1 goto npmfallback
set "npm_config_store_dir=%SRC%\.cache\pnpm-store"
call pnpm install --frozen-lockfile
if errorlevel 1 call pnpm install
goto installed
:npmfallback
call npm install --no-package-lock --no-audit --no-fund
:installed
popd
if not exist "%SRC%\node_modules\vite\bin\vite.js" goto installfail

:build
rem ---------- [2/3] сборка: результат лежит в source\build ----------
echo [2/3] Собираю сайт в source\build ...
pushd "%SRC%"
call npm run build -- --outDir build
set "BUILD_RC=%errorlevel%"
popd
if not "%BUILD_RC%"=="0" goto buildfail
if not exist "%SRC%\build\index.html" goto buildfail

rem ---------- [3/3] локальный сервер + Chrome ----------
netstat -ano | findstr /c:":%PORT% " >nul 2>&1
if not errorlevel 1 goto portbusy

echo [3/3] Поднимаю локальный сервер на порту %PORT% (отдельное окно)...
set "SERVE=%SRC%\.cache\serve.bat"
> "%SERVE%" echo @echo off
>>"%SERVE%" echo cd /d "%SRC%"
>>"%SERVE%" echo title Vite preview - source\build [%PORT%]
>>"%SERVE%" echo call npm run preview -- --outDir build --port %PORT% --strictPort
>>"%SERVE%" echo if errorlevel 1 pause
start "Vite preview" cmd /k "%SERVE%"

rem Жду, пока сервер ответит (не дольше 30 секунд).
where curl.exe >nul 2>&1
if errorlevel 1 goto nocurl
set /a WAIT_N = 0
:wait
curl -s -o nul --max-time 2 "%URL%"
if not errorlevel 1 goto openchrome
set /a WAIT_N += 1
if %WAIT_N% geq 30 goto waitfail
timeout /t 1 /nobreak >nul
goto wait
:nocurl
timeout /t 5 /nobreak >nul
goto openchrome

:portbusy
echo [i] Порт %PORT% уже занят - используется запущенный сервер.
echo     Если страница выглядит устаревшей, закройте окно
echo     "Vite preview" и запустите preview.bat ещё раз.
goto openchrome

:openchrome
set "CHROME="
for /f "delims=" %%C in ('where chrome.exe 2^>nul') do if not defined CHROME set "CHROME=%%C"
if defined CHROME goto chromestart
if exist "%ProgramFiles%\Google\Chrome\Application\chrome.exe" set "CHROME=%ProgramFiles%\Google\Chrome\Application\chrome.exe"
if defined CHROME goto chromestart
if exist "%ProgramFiles(x86)%\Google\Chrome\Application\chrome.exe" set "CHROME=%ProgramFiles(x86)%\Google\Chrome\Application\chrome.exe"
if defined CHROME goto chromestart
if exist "%LocalAppData%\Google\Chrome\Application\chrome.exe" set "CHROME=%LocalAppData%\Google\Chrome\Application\chrome.exe"
if defined CHROME goto chromestart
echo [!] Google Chrome не найден - открываю браузер по умолчанию.
start "" "%URL%"
goto done
:chromestart
start "" "%CHROME%" "%URL%"

:done
echo.
echo Готово.
echo   Сайт:    %URL%
echo   Сборка:  source\build\
echo   Сервер:  окно "Vite preview" - не закрывайте (остановка - Ctrl+C).
echo.
pause
exit /b 0

:waitfail
echo [x] Сервер не поднялся на порту %PORT% за30 секунд.
echo     Посмотрите окно "Vite preview" - там текст ошибки.
pause
exit /b 1

:installfail
echo [x] Не удалось установить зависимости (source\node_modules\vite не найден).
echo     Смотрите вывод npm/pnpm выше.
pause
exit /b 1

:buildfail
echo [x] Сборка не удалась или не создала source\build\index.html.
echo     Смотрите вывод выше (обычно это ошибка в source\src или npm run build).
pause
exit /b 1

:nonode
echo [x] Node.js не найден. Установите Node.js20+ с https://nodejs.org и повторите.
pause
exit /b 1

:nonpm
echo [x] npm не найден. npm поставляется вместе с Node.js - переустановите Node.js.
pause
exit /b 1

:nosource
echo [x] Не найден source\package.json.
echo     Положите экспорт Figma Make в папку source\ и запустите preview.bat снова.
pause
exit /b 1
