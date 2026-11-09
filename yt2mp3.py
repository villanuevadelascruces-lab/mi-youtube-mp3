#!/usr/bin/env python3
"""
YouTube to MP3 Downloader
Downloads YouTube videos as MP3 files using yt-dlp and ffmpeg.
"""

import os
import sys
import subprocess
from pathlib import Path

def download_video(url, output_dir=".", no_playlist=False):
    """
    Download a YouTube video or playlist as MP3 using yt-dlp and ffmpeg with live progress.
    """
    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)
    
    cmd = [
        r'C:\Python314\python.exe', '-m', 'yt_dlp',
        '--extract-audio',
        '--audio-format', 'mp3',
        '--audio-quality', '192',
        '--output', str(output_path / '%(title)s.%(ext)s'),
    ]
    
    if no_playlist:
        cmd.append('--no-playlist')
    
    cmd.append(url)
    
    try:
        env = os.environ.copy()
        ffmpeg_bin = r"C:\Users\las_c\AppData\Local\hermes\tools\ffmpeg-9.0.1-win32-x64\bin"
        env["PATH"] = ffmpeg_bin + os.pathsep + env.get("PATH", "")
        
        result = subprocess.run(
            cmd,
            cwd=os.path.dirname(__file__),
            env=env
        )
        return result.returncode == 0
    except Exception as e:
        print(f"Exception during download: {e}")
        return False


import concurrent.futures

def main():
    print("========================================")
    print("      DESCARGADOR DE YOUTUBE A MP3      ")
    print("========================================")
    
    # Determine output directory
    default_output_dir = os.path.join(os.path.dirname(__file__), "Música descargada")
    output_dir = default_output_dir
    
    # Ask for output directory only once at start
    try:
        user_input = input("Introduce la carpeta de salida (deja en blanco para usar la predeterminada): ").strip()
        if user_input:
            output_dir = user_input
    except EOFError:
        pass  # Use default if input fails
    
    while True:
        print(f"\n📂 Carpeta de salida actual: {os.path.abspath(output_dir)}")
        print("Pega las URLs de YouTube o Playlists (una por línea o varias separadas por espacio).")
        print("Deja en blanco y pulsa Enter para iniciar la descarga.\n")
        
        urls = []
        while True:
            try:
                line = input("URL (o Enter para iniciar): ").strip()
                if not line:
                    break
                for u in line.split():
                    urls.append(u)
            except EOFError:
                break
        
        if not urls:
            print("\n❌ No se proporcionó ninguna URL.")
            continue
        
        # Process each URL and determine if no_playlist should be True
        download_items = []
        for url in urls:
            no_playlist = True
            if 'playlist?list=' in url:
                no_playlist = False
            elif 'watch?v=' in url and 'list=' in url:
                print(f"\n🔗 Enlace con vídeo y playlist: {url}")
                choice = input("¿Qué deseas descargar?\n  [1] Solo esta canción (Por defecto)\n  [2] Toda la playlist completa\nElige [1/2] (1): ").strip()
                if choice == '2':
                    no_playlist = False
                else:
                    no_playlist = True
            
            download_items.append((url, no_playlist))
        
        print(f"\n🚀 Iniciando {len(download_items)} descarga(s)...\n")
        
        # Download concurrently using ThreadPoolExecutor
        success_count = 0
        with concurrent.futures.ThreadPoolExecutor(max_workers=4) as executor:
            future_to_url = {executor.submit(download_video, url, output_dir, no_pl): url for url, no_pl in download_items}
            for future in concurrent.futures.as_completed(future_to_url):
                url = future_to_url[future]
                try:
                    success = future.result()
                    if success:
                        print(f"\n✅ Completado: {url}")
                        success_count += 1
                    else:
                        print(f"\n❌ Falló: {url}")
                except Exception as exc:
                    print(f"\n❌ {url} generó una excepción: {exc}")
        
        print(f"\n========================================")
        print(f" Resumen: {success_count}/{len(download_items)} descargados con éxito.")
        print(f"========================================")
        
        # Preguntar qué hacer a continuación
        print("\n¿Qué deseas hacer ahora?")
        print("  [1] Descargar más URLs (misma carpeta)")
        print("  [2] Cambiar carpeta de salida y descargar más URLs")
        print("  [3] Salir")
        choice = input("\nElige [1/2/3] (3): ").strip()
        
        if choice == '1':
            continue  # Volver a pedir URLs
        elif choice == '2':
            new_dir = input("Introduce la nueva ruta de salida (o Enter para usar la actual): ").strip()
            if new_dir:
                output_dir = new_dir
            continue  # Volver a pedir URLs
        else:
            print("\n¡Hasta luego!")
            break

if __name__ == "__main__":
    main()