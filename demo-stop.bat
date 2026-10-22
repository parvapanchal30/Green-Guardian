@echo off
rem Stops the two GreenGuardian demo servers started by demo.bat.
rem It stops only processes whose command line is exactly the demo API (uvicorn app.main:create_app ... --port 8000) or the
rem demo web app (vite ... --port 5173), together with the console windows that launched them. Nothing else is touched.
powershell -NoProfile -Command "$pat = 'uvicorn app.main:create_app.*--port 8000|vite.*--port 5173|npm run dev -- --port 5173'; $n = 0; Get-CimInstance Win32_Process | Where-Object { $_.CommandLine -match $pat -and $_.ProcessId -ne $PID } | ForEach-Object { & taskkill /PID $_.ProcessId /T /F *> $null; $n++ }; Write-Host ('stopped ' + $n + ' process(es)')"
echo GreenGuardian demo servers stopped (if any were running).
pause
