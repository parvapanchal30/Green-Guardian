@echo off
rem Stops the two GreenGuardian demo servers started by demo.bat.
rem It stops only processes whose command line is exactly the demo API (uvicorn app.main:create_app --factory --host
rem 127.0.0.1 --port 8000) or the demo web app (vite --port 5173 --strictPort), as demo.bat starts them. A backend or
rem frontend you start yourself (for example with --reload, or plain npm run dev) does not match and is never touched.
powershell -NoProfile -Command "$pat = 'uvicorn app.main:create_app --factory --host 127.0.0.1 --port 8000|vite\.js\W{0,3}--port 5173 --strictPort|npm run dev -- --port 5173 --strictPort'; $n = 0; Get-CimInstance Win32_Process | Where-Object { $_.CommandLine -match $pat -and $_.ProcessId -ne $PID } | ForEach-Object { & taskkill /PID $_.ProcessId /T /F *> $null; $n++ }; Write-Host ('stopped ' + $n + ' process(es)')"
echo GreenGuardian demo servers stopped (if any were running).
pause
