@echo off
setlocal EnableExtensions
title GreenGuardian local demo
rem ---------------------------------------------------------------------------------------------------------------
rem  GreenGuardian local demo launcher.
rem    demo.bat              start (creates the demo data the first time), then offers the automated tour
rem    demo.bat --fresh      throw the demo data away and rebuild it
rem    demo.bat --offline    use made-up weather instead of the real forecast (no internet needed)
rem    tour.bat              replay the automated browser tour any time
rem    demo-stop.bat         stop the demo's API, web app and background worker
rem  Everything runs on THIS computer with a throwaway SQLite file (backend\var\demo\demo.db). The plants and records
rem  are examples, but the weather is the real Open-Meteo forecast for their coordinates (unless offline), and a
rem  background worker runs the scheduled agent checks and recurring inspections, as it would in production.
rem  It never reads or writes your Supabase / hosted database, and needs no cloud account.
rem ---------------------------------------------------------------------------------------------------------------
cd /d "%~dp0"
set "ROOT=%~dp0"
set "BACK=%ROOT%backend"
set "FRONT=%ROOT%frontend"
set "PY=%BACK%\.venv\Scripts\python.exe"
set "API_PORT=8000"
set "WEB_PORT=5173"

rem ---- options (in any order) ----------------------------------------------------------------------------------
set "FRESH="
set "OFFLINE="
:args
if "%~1"=="" goto :argsdone
if /i "%~1"=="--fresh" set "FRESH=1"
if /i "%~1"=="--offline" set "OFFLINE=1"
shift
goto :args
:argsdone

echo.
echo  === GreenGuardian local demo ===
echo.

rem ---- prerequisites -------------------------------------------------------------------------------------------
where node >nul 2>nul || ( echo [!] Node.js was not found. Install Node 22 or newer from https://nodejs.org and run this again. & goto :fail )
if not exist "%PY%" (
  echo [!] The backend virtual environment is missing: %PY%
  echo     Create it once with:
  echo        cd backend
  echo        python -m venv .venv
  echo        .venv\Scripts\python.exe -m pip install -e ".[dev]"
  goto :fail
)
if not exist "%FRONT%\node_modules" (
  echo [..] Installing frontend packages once ^(npm ci^) ...
  pushd "%FRONT%" && call npm ci && popd
  if errorlevel 1 ( echo [!] npm ci failed. & goto :fail )
)

rem ---- ports must be free --------------------------------------------------------------------------------------
powershell -NoProfile -Command "if (Get-NetTCPConnection -LocalPort %API_PORT% -State Listen -ErrorAction SilentlyContinue) { exit 1 }"
if errorlevel 1 ( echo [!] Port %API_PORT% is already in use. Run demo-stop.bat, or close the program using it. & goto :fail )
powershell -NoProfile -Command "if (Get-NetTCPConnection -LocalPort %WEB_PORT% -State Listen -ErrorAction SilentlyContinue) { exit 1 }"
if errorlevel 1 ( echo [!] Port %WEB_PORT% is already in use. Run demo-stop.bat, or close the program using it. & goto :fail )

rem ---- settings for THIS demo only (the backend\.env file with your real database is overridden) --------------
set "DATABASE_URL=sqlite+pysqlite:///var/demo/demo.db"
set "JWT_SECRET=demo-only-local-secret-not-for-real-use-0123456789"
set "ENV=development"
rem Real weather from Open-Meteo (free, no key, non-commercial use: ADR-065) when it can be reached; otherwise made up.
set "WEATHER_PROVIDER=mock"
set "WEATHER_NOTE=made-up weather (offline mode)"
if not defined OFFLINE (
  powershell -NoProfile -Command "try { $r = Invoke-WebRequest 'https://api.open-meteo.com/v1/forecast?latitude=19.13&longitude=72.91&hourly=temperature_2m&forecast_days=1' -UseBasicParsing -TimeoutSec 8; if ($r.StatusCode -eq 200) { exit 0 } else { exit 1 } } catch { exit 1 }"
  if errorlevel 1 (
    set "WEATHER_NOTE=made-up weather: Open-Meteo could not be reached, so the demo works offline"
  ) else (
    set "WEATHER_PROVIDER=open_meteo"
    set "WEATHER_NOTE=real weather from Open-Meteo for the demo plants' coordinates"
  )
)
set "STORAGE_PROVIDER=local"
set "STORAGE_LOCAL_DIR=var/demo/storage"

if defined FRESH (
  echo [..] Removing the old demo data ...
  if exist "%BACK%\var\demo" rmdir /s /q "%BACK%\var\demo"
)
if not exist "%BACK%\var\demo" mkdir "%BACK%\var\demo"

if not exist "%BACK%\var\demo\demo.db" (
  echo [..] Building the demo data ^(migrations + two workspaces, about 20 seconds^) ...
  pushd "%BACK%"
  "%PY%" -m app.tools.demo_seed >"%BACK%\var\demo\seed.log" 2>&1
  if errorlevel 1 (
    popd
    echo [!] The demo data could not be built. Last lines of backend\var\demo\seed.log:
    powershell -NoProfile -Command "Get-Content '%BACK%\var\demo\seed.log' -Tail 8"
    goto :fail
  )
  popd
)

rem ---- an existing demo database is brought up to date (new tables only; the demo data is kept) -------------
pushd "%BACK%"
"%PY%" -m alembic upgrade head >"%BACK%\var\demo\upgrade.log" 2>&1
if errorlevel 1 (
  popd
  echo [!] The demo database could not be updated. Last lines of backend\var\demo\upgrade.log:
  powershell -NoProfile -Command "Get-Content '%BACK%\var\demo\upgrade.log' -Tail 8"
  goto :fail
)
popd

rem ---- start the two servers in their own windows ---------------------------------------------------------------
echo [..] Starting the API on http://127.0.0.1:%API_PORT% ...
start "GreenGuardian API (demo)" /d "%BACK%" cmd /k ""%PY%" -m uvicorn app.main:create_app --factory --host 127.0.0.1 --port %API_PORT%"
echo [..] Starting the web app on http://localhost:%WEB_PORT% ...
start "GreenGuardian web (demo)" /d "%FRONT%" cmd /k "npm run dev -- --port %WEB_PORT% --strictPort"
echo [..] Starting the background worker ^(scheduled agent checks, recurring inspections^) ...
start "GreenGuardian worker (demo)" /d "%BACK%" cmd /k ""%PY%" -m app.worker --label gg-demo"

echo [..] Waiting for both to answer ...
set /a TRIES=0
:wait
set /a TRIES+=1
powershell -NoProfile -Command "try { $a=(Invoke-WebRequest http://127.0.0.1:%API_PORT%/healthz -UseBasicParsing -TimeoutSec 2).StatusCode; $w=(Invoke-WebRequest http://localhost:%WEB_PORT%/ -UseBasicParsing -TimeoutSec 2).StatusCode; if ($a -eq 200 -and $w -eq 200) { exit 0 } else { exit 1 } } catch { exit 1 }"
if not errorlevel 1 goto :ready
if %TRIES% GEQ 40 ( echo [!] The servers did not come up. Look at the two new windows for the error. & goto :fail )
timeout /t 2 /nobreak >nul
goto :wait

:ready
echo [ok] Ready. Weather: %WEATHER_NOTE%.
if not defined GG_NO_BROWSER start "" "http://localhost:%WEB_PORT%/"
echo.
echo  ---------------------------------------------------------------------------------------------------
type "%BACK%\var\demo\DEMO_LOGIN.txt"
echo  ---------------------------------------------------------------------------------------------------
echo.
echo  The demo is running. Next, an automated tour can drive a browser window through the product by itself
echo  ^(17 short steps, about 3 minutes, with a caption on screen for each; it only looks, it saves nothing^).
echo.
choice /C YN /N /M "  Run the automated tour now? [Y/N] "
if errorlevel 2 goto :later
call "%ROOT%tour.bat"
:later
echo.
echo  To replay the tour any time:  tour.bat      ^(options: tour.bat --manual, tour.bat --speed 2^)
echo  To click around by hand:      see docs\DEMO.md or open http://localhost:%WEB_PORT%/
echo  To stop everything:           demo-stop.bat
echo  To rebuild the demo data:     demo.bat --fresh
echo  Without internet:             demo.bat --offline
echo.
pause
exit /b 0

:fail
echo.
pause
exit /b 1
