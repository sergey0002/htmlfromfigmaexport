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
rem  Не удаляйте source\ и пользовательские данные без явного согласия.
rem  В корне репозитория артефакты не появляются (они в .gitignore).
rem  Установка зависимостей повторяет tools/audit_runner.package_install:
rem  --ignore-scripts, ровно один lock-файл, версия pnpm из packageManager
rem  или .mise.toml (иначе npx pnpm@версия / понятная ошибка).
rem ============================================================

cd /d "%~dp0"
set "ROOT=%CD%"
set "SRC=%ROOT%\source"
set "PORT=8084"
set "URL=http://localhost:%PORT%/"

rem Этот вспомогательный скрипт НЕ песочница и не доказательство происхождения.
echo [!] ВНИМАНИЕ: запуск выполняет npm build/preview и код экспорта без изоляции.
echo     Скрипт изменит source\node_modules, source\build и source\.cache.
echo     Используйте только доверенный экспорт, без секретов и чувствительных сервисов.
choice /C YN /N /M "Продолжить на свой риск? [Y/N] "
if errorlevel 2 exit /b 1
netstat -ano | findstr /c:":%PORT% " >nul 2>&1
if not errorlevel 1 goto portbusy

rem Кэш npm - строго внутрь source, чтобы npm не писал вне него.
set "npm_config_cache=%SRC%\.cache\npm"

where node >nul 2>&1
if errorlevel 1 goto nonode
where npm >nul 2>&1
if errorlevel 1 goto nonpm
if not exist "%SRC%\package.json" goto nosource

rem ---------- [1/3] зависимости: механика tools/audit_runner.package_install ----------
rem Ровно один lock-файл; npm ci / pnpm install --frozen-lockfile --ignore-scripts;
rem версия pnpm: packageManager, затем .mise.toml, иначе ошибка (как в движке).
if exist "%SRC%\node_modules\vite\bin\vite.js" goto build
echo [1/3] Устанавливаю зависимости в source\node_modules ...
pushd "%SRC%"
set "HAS_PNPM_LOCK=0"
set "HAS_NPM_LOCK=0"
if exist "pnpm-lock.yaml" set "HAS_PNPM_LOCK=1"
if exist "package-lock.json" set "HAS_NPM_LOCK=1"
if "%HAS_PNPM_LOCK%"=="%HAS_NPM_LOCK%" goto badlocks
set "npm_config_ignore_scripts=true"
set "npm_config_audit=false"
set "npm_config_fund=false"
if "%HAS_NPM_LOCK%"=="1" goto inst_npmci
where pnpm >nul 2>&1
if not errorlevel 1 goto inst_pnpm
set "PM_LINE="
set "PNPM_VER="
set "V="
for /f "usebackq delims=" %%A in (`findstr /c:"packageManager" "package.json" 2^>nul`) do set "PM_LINE=%%A"
set "V=%PM_LINE:*pnpm@=%"
set "V=%V:"=%"
for /f "tokens=1 delims=," %%T in ("%V%") do set "V=%%T"
echo %V%| findstr /r /x "[0-9][0-9]*\.[0-9][0-9]*\.[0-9][0-9]*" >nul 2>&1 && set "PNPM_VER=%V%"
if defined PNPM_VER goto inst_npx
set "V="
for /f "tokens=2 delims==" %%T in ('findstr /c:"npm:pnpm" ".mise.toml" 2^>nul') do set "V=%%T"
set "V=%V:"=%"
for /f "tokens=1" %%T in ("%V%") do set "V=%%T"
echo %V%| findstr /r /x "[0-9][0-9]*\.[0-9][0-9]*\.[0-9][0-9]*" >nul 2>&1 && set "PNPM_VER=%V%"
if not defined PNPM_VER goto noversion
goto inst_npx
:inst_npmci
call npm ci --ignore-scripts --no-audit --no-fund
goto installed
:inst_pnpm
set "npm_config_store_dir=%SRC%\.cache\pnpm-store"
call pnpm install --frozen-lockfile --ignore-scripts
goto installed
:inst_npx
set "npm_config_store_dir=%SRC%\.cache\pnpm-store"
call npx --yes pnpm@%PNPM_VER% install --frozen-lockfile --ignore-scripts
goto installed
:installed
popd
set "npm_config_ignore_scripts="
set "npm_config_audit="
set "npm_config_fund="
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
echo [x] Порт %PORT% занят. Не открываю неизвестный listener как эталон.
echo     Остановите занимающий порт процесс и повторите запуск.
pause
exit /b 1

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

:badlocks
popd
echo [x] Нужен ровно один pnpm-lock.yaml или package-lock.json (как в tools).
echo     Сейчас в source\: pnpm-lock=%HAS_PNPM_LOCK%, package-lock=%HAS_NPM_LOCK%.
pause
exit /b 1

:noversion
popd
set "npm_config_ignore_scripts="
set "npm_config_audit="
set "npm_config_fund="
echo [x] pnpm не найден в PATH, а версию определить не удалось.
echo     Установите pnpm или укажите его точную версию в packageManager/.mise.toml.
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
