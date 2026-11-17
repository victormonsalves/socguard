@echo off
setlocal
cd /d "%~dp0"
echo [%date% %time%] Ejecutando pasada de inspeccion SOCGuard... >> logs\scheduler_exec.log
python main.py --run-once >> logs\scheduler_exec.log 2>&1
exit /b %ERRORLEVEL%
