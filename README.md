# YT2MP3 — Descargador de YouTube a MP3

Descarga vídeos y playlists de YouTube como archivos MP3 (192 kbps), con etiquetas de metadatos y carátula incluidas automáticamente.

## Instalación (la forma fácil)

1. Descarga el proyecto: botón verde **Code → Download ZIP** y descomprímelo donde quieras.
2. Entra en la carpeta descomprimida y haz doble clic en **`instalar.bat`**.
3. Espera a que termine. Al acabar tendrás el icono **YT2MP3** en tu escritorio, listo para usar.

El instalador se encarga de todo por ti:

- Instala **Python** si no está en el equipo (sin permisos de administrador)
- Crea un **entorno virtual** con **yt-dlp**
- Descarga **FFmpeg** en la carpeta del proyecto (necesario para convertir a MP3)
- Crea el **acceso directo en el escritorio**

> 💡 Si Windows muestra *"Windows protegió tu PC"* (SmartScreen) al ejecutar el instalador,
> pulsa **Más información → Ejecutar de todas formas**. Es el aviso estándar para archivos recién descargados.

## Uso

Haz doble clic en el icono **YT2MP3** del escritorio (o en `yt2mp3.bat` dentro de la carpeta):

1. Elige la carpeta de salida (con Enter se usa `Música descargada`, dentro de la propia carpeta del programa).
2. Pega las URLs de YouTube —una por línea o varias separadas por espacios— y pulsa Enter.
3. Si un enlace contiene vídeo **y** playlist a la vez, podrás elegir qué descargar.
4. Al terminar, el resumen muestra cuántas descargas tuvieron éxito y puedes seguir añadiendo URLs o salir.

Las descargas se hacen en paralelo (hasta 4 a la vez).

## Actualizar

YouTube cambia con frecuencia y a veces yt-dlp necesita actualizarse. Basta con volver a
ejecutar **`instalar.bat`**: actualizará yt-dlp sin repetir las descargas grandes (Python y FFmpeg).

## Desinstalar

No hay desinstalador: la app vive en su propia carpeta. Borra la carpeta del proyecto y el
acceso directo `YT2MP3` del escritorio, y listo. El resto del sistema queda intacto.

## Desarrollo

Si prefieres ejecutar el proyecto a mano (sin el instalador):

```bash
pip install -r requirements.txt
python yt2mp3.py
```

Requisitos: Python 3.9+ y FFmpeg accesible en el `PATH` (o en la carpeta `ffmpeg\` del proyecto).

## Estructura

| Archivo | Descripción |
|---|---|
| `instalar.bat` | Instalador automático para Windows |
| `yt2mp3.bat` | Lanzador de la aplicación |
| `yt2mp3.py` | Aplicación (descargas, conversión a MP3) |
| `requirements.txt` | Dependencias de Python |
| `icon.ico` | Icono del acceso directo |

## Licencia

Consulta el archivo [LICENSE](LICENSE).
