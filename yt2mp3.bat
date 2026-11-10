@echo off
chcp 65001 >nul
title YT2MP3 - Descargador de YouTube a MP3
cd /d "%~dp0"

rem 1) Usar el entorno virtual creado por instalar.bat
rem 2) Si no existe, probar con python / py del sistema
rem    (se usa --version para evitar el "stub" falso de la Tienda)
set "PYEXE="
if exist ".venv\Scripts\python.exe" set "PYEXE=.venv\Scripts\python.exe"
if not defined PYEXE python --version >nul 2>&1 && set "PYEXE=python"
if not defined PYEXE py -3 --version >nul 2>&1 && set "PYEXE=py -3"

if not defined PYEXE (
    echo.
    echo  No se encontro Python en este equipo.
    echo  Ejecuta instalar.bat primero para configurar la aplicacion.
    echo.
    pause
    exit /b 1
)

%PYEXE% yt2mp3.py %*
pause
