@echo off
rem ============================================================
rem  YT2MP3 - Instalador automatico (Windows)
rem  - Instala Python si falta
rem  - Crea un entorno virtual con yt-dlp
rem  - Descarga FFmpeg en la carpeta del proyecto
rem  - Crea el acceso directo "YT2MP3" en el escritorio
rem  No necesita permisos de administrador.
rem ============================================================
setlocal
chcp 65001 >nul 2>&1
title YT2MP3 - Instalador
cd /d "%~dp0"

echo.
echo  ============================================================
echo    YT2MP3 - DESCARGADOR DE YOUTUBE A MP3 (INSTALADOR)
echo  ============================================================
echo.
echo  Este instalador configurara todo automaticamente:
echo.
echo    [1/4] Python            (solo si falta en tu equipo)
echo    [2/4] Entorno y librerias (yt-dlp)
echo    [3/4] FFmpeg            (para convertir a MP3)
echo    [4/4] Icono en el escritorio
echo.
echo  No necesitas hacer nada. Puede tardar unos minutos
echo  si es la primera vez (descarga unos 110 MB en total).
echo  No se pide permiso de administrador y no se toca nada
echo  del resto de tu sistema.
echo.

rem ============================================================
rem [1/4] PYTHON
rem ============================================================
call :detect_python
if defined PYEXE goto :deps

echo  [1/4] Python no esta instalado. Se instalara ahora.
where.exe winget >nul 2>&1
if not errorlevel 1 (
    echo        Instalando Python con winget...
    winget install -e --id Python.Python.3.14 --scope user --silent --accept-source-agreements --accept-package-agreements
    call :refresh_path
    call :detect_python
)
if defined PYEXE goto :deps

echo        Descargando instalador de Python desde python.org...
curl -L --fail --retry 3 --retry-delay 2 -o "%TEMP%\yt2mp3_python.exe" "https://www.python.org/ftp/python/3.14.7/python-3.14.7-amd64.exe"
if errorlevel 1 goto :err_red
echo        Instalando Python...
"%TEMP%\yt2mp3_python.exe" /quiet InstallAllUsers=0 PrependPath=1 Shortcuts=0
if errorlevel 1 goto :err_python
call :refresh_path
call :detect_python
if defined PYEXE goto :deps

echo.
echo  [X] No se pudo instalar Python automaticamente.
echo      Instalalo manualmente desde https://www.python.org/downloads/
echo      (importante: marca la casilla "Add python.exe to PATH")
echo      y vuelve a ejecutar este instalador.
echo.
pause
exit /b 1

rem ============================================================
rem [2/4] ENTORNO VIRTUAL Y LIBRERIAS
rem ============================================================
:deps
echo  [1/4] Python detectado:
echo        %PYEXE%
echo.
if not exist "%~dp0.venv\Scripts\python.exe" (
    echo  [2/4] Creando el entorno virtual del proyecto...
    "%PYEXE%" -m venv "%~dp0.venv"
    if errorlevel 1 (
        echo  [X] No se pudo crear el entorno virtual.
        pause
        exit /b 1
    )
)
set "VPY=%~dp0.venv\Scripts\python.exe"

echo  [2/4] Instalando/actualizando librerias (yt-dlp)...
"%VPY%" -m pip install --upgrade pip
"%VPY%" -m pip install --upgrade -r "%~dp0requirements.txt"
if errorlevel 1 (
    echo  [X] No se pudieron instalar las librerias.
    echo      Comprueba tu conexion a internet y vuelve a intentarlo.
    pause
    exit /b 1
)
"%VPY%" -m yt_dlp --version
if errorlevel 1 (
    echo  [X] yt-dlp no quedo bien instalado.
    pause
    exit /b 1
)
echo.

rem ============================================================
rem [3/4] FFMPEG
rem ============================================================
if exist "%~dp0ffmpeg\bin\ffmpeg.exe" (
    echo  [3/4] FFmpeg ya esta instalado en el proyecto.
    goto :shortcut
)
where.exe ffmpeg >nul 2>&1
if not errorlevel 1 (
    echo  [3/4] FFmpeg ya esta disponible en el sistema.
    goto :shortcut
)

echo  [3/4] Descargando FFmpeg (unos 110 MB, solo la primera vez)...
curl -L --fail --retry 3 --retry-delay 2 -o "%TEMP%\yt2mp3_ffmpeg.zip" "https://www.gyan.dev/ffmpeg/builds/ffmpeg-release-essentials.zip"
if errorlevel 1 (
    echo        Fuente principal no disponible, probando alternativa...
    curl -L --fail --retry 3 --retry-delay 2 -o "%TEMP%\yt2mp3_ffmpeg.zip" "https://github.com/BtbN/FFmpeg-Builds/releases/latest/download/ffmpeg-master-latest-win64-gpl.zip"
)
if errorlevel 1 goto :err_red

echo        Preparando FFmpeg...
set "FFEXT=%TEMP%\yt2mp3_ffmpeg_extract"
if exist "%FFEXT%" rmdir /s /q "%FFEXT%"
mkdir "%FFEXT%"
tar -xf "%TEMP%\yt2mp3_ffmpeg.zip" -C "%FFEXT%"
if errorlevel 1 (
    powershell -NoProfile -Command "Expand-Archive -LiteralPath $env:TEMP\yt2mp3_ffmpeg.zip -DestinationPath $env:TEMP\yt2mp3_ffmpeg_extract -Force"
)
set "FFSRC="
if exist "%FFEXT%\bin\ffmpeg.exe" set "FFSRC=%FFEXT%"
for /d %%D in ("%FFEXT%\ffmpeg-*") do if exist "%%D\bin\ffmpeg.exe" set "FFSRC=%%D"
if not defined FFSRC (
    echo  [X] El paquete de FFmpeg descargado no es valido.
    pause
    exit /b 1
)
if exist "%~dp0ffmpeg" rmdir /s /q "%~dp0ffmpeg"
move "%FFSRC%" "%~dp0ffmpeg" >nul
if not exist "%~dp0ffmpeg\bin\ffmpeg.exe" (
    echo  [X] No se pudo preparar FFmpeg en la carpeta del proyecto.
    pause
    exit /b 1
)
del "%TEMP%\yt2mp3_ffmpeg.zip" >nul 2>&1
if exist "%FFEXT%" rmdir /s /q "%FFEXT%" >nul 2>&1
echo        FFmpeg instalado en la carpeta del proyecto.
echo.

rem ============================================================
rem [4/4] ACCESO DIRECTO EN EL ESCRITORIO
rem ============================================================
:shortcut
echo  [4/4] Creando el acceso directo en el escritorio...
set "YT2MP3_DIR=%~dp0"
powershell -NoProfile -Command "try { $ws = New-Object -ComObject WScript.Shell; $desktop = [Environment]::GetFolderPath('Desktop'); $lnk = Join-Path $desktop 'YT2MP3.lnk'; $s = $ws.CreateShortcut($lnk); $s.TargetPath = Join-Path $env:YT2MP3_DIR 'yt2mp3.bat'; $s.WorkingDirectory = $env:YT2MP3_DIR; $s.IconLocation = Join-Path $env:YT2MP3_DIR 'icon.ico'; $s.Description = 'Descargador de YouTube a MP3'; $s.Save(); exit 0 } catch { exit 1 }"
if errorlevel 1 (
    echo  [!] No se pudo crear el acceso directo automaticamente.
    echo      Puedes usar la app con doble clic en yt2mp3.bat
) else (
    echo        Acceso directo "YT2MP3" creado en tu escritorio.
)

echo.
echo  ============================================================
echo                 INSTALACION COMPLETADA
echo  ============================================================
echo.
echo  Ya puedes cerrar esta ventana y abrir la app haciendo
echo  doble clic en el icono YT2MP3 de tu escritorio.
echo.
echo  Para actualizar la app en el futuro, vuelve a ejecutar
echo  instalar.bat (no descarga nada de nuevo salvo novedades).
echo.
choice /C SN /N /M "Quieres abrir YT2MP3 ahora? [S/N] "
if errorlevel 2 goto :fin
start "YT2MP3" "%~dp0yt2mp3.bat"

:fin
echo.
echo  Listo. Hasta luego.
timeout /t 3 >nul 2>&1
exit /b 0

rem ============================================================
rem SUBRUTINAS
rem ============================================================

:detect_python
rem Busca un Python util (evita el "stub" de la Tienda de Windows)
set "PYEXE="
python --version >nul 2>&1 && for /f "usebackq delims=" %%I in (`python -c "import sys; print(sys.executable)" 2^>nul`) do set "PYEXE=%%I"
if not defined PYEXE py -3 --version >nul 2>&1 && for /f "usebackq delims=" %%I in (`py -3 -c "import sys; print(sys.executable)" 2^>nul`) do set "PYEXE=%%I"
if not defined PYEXE for /d %%D in ("%LOCALAPPDATA%\Programs\Python\Python3*") do if exist "%%D\python.exe" set "PYEXE=%%D\python.exe"
if not defined PYEXE for /d %%D in ("%ProgramFiles%\Python3*") do if exist "%%D\python.exe" set "PYEXE=%%D\python.exe"
exit /b 0

:refresh_path
rem Vuelve a leer el PATH del registro (tras instalar Python)
for /f "usebackq delims=" %%P in (`powershell -NoProfile -Command "[Environment]::GetEnvironmentVariable('Path','User')"`) do set "P_USER=%%P"
for /f "usebackq delims=" %%P in (`powershell -NoProfile -Command "[Environment]::GetEnvironmentVariable('Path','Machine')"`) do set "P_MACHINE=%%P"
if defined P_USER set "PATH=%P_USER%;%PATH%"
if defined P_MACHINE set "PATH=%P_MACHINE%;%PATH%"
exit /b 0

:err_red
echo.
echo  [X] Error de descarga. Comprueba tu conexion a internet
echo      y vuelve a ejecutar este instalador.
echo.
pause
exit /b 1

:err_python
echo.
echo  [X] El instalador de Python devolvio un error.
echo      Ejecutalo a mano para ver el motivo: %TEMP%\yt2mp3_python.exe
echo      (o instala Python desde https://www.python.org/downloads/)
echo.
pause
exit /b 1
