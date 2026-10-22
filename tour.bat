@echo off
setlocal EnableExtensions
title GreenGuardian automated tour
rem Replays the automated browser tour against the demo that demo.bat started.
rem   tour.bat                 full tour, advances by itself
rem   tour.bat --manual        waits for Enter between steps
rem   tour.bat --speed 2       twice as fast (0.5 = slower)
rem   tour.bat --only agent,map     only some steps (ids are listed in frontend\tour\steps.json)
cd /d "%~dp0frontend"
where node >nul 2>nul || ( echo Node.js was not found. Install Node 22 or newer from https://nodejs.org & pause & exit /b 1 )
if not exist node_modules ( echo Frontend packages are missing. Run demo.bat first. & pause & exit /b 1 )
echo.
echo  A browser window will open and drive itself through the product. Leave the mouse alone; it takes a few minutes.
echo.
call npm run tour -- %*
set RC=%ERRORLEVEL%
echo.
if not "%RC%"=="0" echo  The tour reported a problem ^(code %RC%^). Is the demo running? Start it with demo.bat.
pause
exit /b %RC%
