@echo off
rem ============================================================
rem  Lanzador de la interfaz web de YT2MP3
rem  (alternativa al acceso directo "YT2MP3" del escritorio)
rem ============================================================
setlocal
cd /d "%~dp0"

if not exist ".venv\Scripts\pythonw.exe" goto :sin_entorno

start "" ".venv\Scripts\pythonw.exe" "app.py"
exit /b 0

:sin_entorno
echo.
echo  No se encontro el entorno de la aplicacion.
echo  Ejecuta instalar.bat primero (solo hace falta una vez).
echo.
pause
exit /b 1
