#!/usr/bin/env python3
"""
Lógica de descarga de YT2MP3 usando yt-dlp (la comparten la app web y el CLI).

  - analizar enlaces (metadatos para la vista previa)
  - descargar audio y convertirlo a MP3 (con carátula y etiquetas opcionales)
  - informar del progreso mediante un callback
"""

from pathlib import Path

import yt_dlp

BASE_DIR = Path(__file__).resolve().parent
DEFAULT_OUTPUT_DIR = BASE_DIR / "Música descargada"

# Si el usuario deja un cookies.txt junto a la app, se usa automáticamente.
COOKIES_PATH = BASE_DIR / "cookies.txt"

# YouTube a veces pide "inicia sesión para confirmar que no eres un bot" al
# cliente web. Estos clientes alternativos de yt-dlp suelen seguir funcionando.
FALLBACK_CLIENTS = ("android", "web_embedded")

_BOT_CHECK_HINTS = (
    "sign in to confirm",
    "not a bot",
    "cookies for the authentication",
    "confirm you're not a bot",
)


class CancelledError(Exception):
    """Se lanza desde el hook de progreso cuando el usuario cancela."""


def find_ffmpeg_dir():
    """Carpeta con ffmpeg.exe junto al proyecto (la instala instalar.bat), o None."""
    for candidate in (BASE_DIR / "ffmpeg" / "bin", BASE_DIR / "ffmpeg"):
        if (candidate / "ffmpeg.exe").is_file():
            return str(candidate)
    return None


def ffmpeg_available():
    """True si ffmpeg es accesible (local o en el PATH)."""
    if find_ffmpeg_dir():
        return True
    import shutil

    return shutil.which("ffmpeg") is not None


def _base_opts():
    opts = {
        "quiet": True,
        "noprogress": True,
        "no_warnings": True,
        "no_color": True,
        "socket_timeout": 30,
        "retries": 3,
        "fragment_retries": 3,
    }
    ffmpeg_dir = find_ffmpeg_dir()
    if ffmpeg_dir:
        opts["ffmpeg_location"] = ffmpeg_dir
    if COOKIES_PATH.is_file():
        opts["cookiefile"] = str(COOKIES_PATH)
    return opts


def _is_bot_check(error):
    text = str(error).lower()
    return any(hint in text for hint in _BOT_CHECK_HINTS)


def _with_fallback(base_opts, action):
    """
    Ejecuta action(opts) y, si YouTube pide verificación, reintenta con los
    clientes alternativos de yt-dlp (el cliente web es el que más se bloquea).
    """
    last_error = None
    for client in (None, *FALLBACK_CLIENTS):
        opts = dict(base_opts)
        if client:
            opts["extractor_args"] = {"youtube": {"player_client": [client]}}
        try:
            return action(opts)
        except (CancelledError, yt_dlp.utils.DownloadCancelled):
            raise
        except Exception as error:  # noqa: BLE001 - se decide según el mensaje
            if not _is_bot_check(error):
                raise
            last_error = error
    raise last_error


def _best_thumbnail(data):
    thumbs = data.get("thumbnails") or []
    for thumb in reversed(thumbs):
        if isinstance(thumb, dict) and thumb.get("url"):
            return thumb["url"]
    return data.get("thumbnail") or ""


def _clean_error(error):
    text = str(error).strip() or error.__class__.__name__
    first = text.splitlines()[0].replace("ERROR: ", "").strip()
    if _is_bot_check(error):
        return (
            "YouTube ha pedido verificación (no eres un bot). "
            "Prueba otra vez en unos minutos; si sigue igual, coloca un "
            "cookies.txt junto a la app."
        )
    return first[:300]


def _extract(url, opts):
    with yt_dlp.YoutubeDL(opts) as ydl:
        return ydl.extract_info(url, download=False)


def _entry_title(entry):
    if not isinstance(entry, dict):
        return ""
    return entry.get("title") or entry.get("url") or ""


def analyze_url(url):
    """
    Analiza una URL y devuelve un dict listo para la vista previa:
      ok, kind ('video'|'playlist'), title, channel, duration, thumbnail,
      has_playlist, playlist_count, error
    """
    info = {
        "url": url,
        "ok": False,
        "kind": "video",
        "title": "",
        "channel": "",
        "duration": 0,
        "thumbnail": "",
        "has_playlist": False,
        "playlist_count": 0,
        "error": "",
    }
    try:
        has_list = "list=" in url
        is_watch = ("watch?" in url and "v=" in url) or "youtu.be/" in url
        is_playlist_only = "playlist?list=" in url or ("/playlist" in url and not is_watch)

        if is_playlist_only:
            opts = {
                **_base_opts(),
                "extract_flat": "in_playlist",
                "skip_download": True,
                "playlist_items": "1",
            }
            data = _with_fallback(opts, lambda variant: _extract(url, variant))
            entries = data.get("entries") or []
            info.update(
                ok=True,
                kind="playlist",
                title=data.get("title") or "Playlist",
                channel=data.get("uploader") or data.get("channel") or "Playlist",
                thumbnail=_best_thumbnail(data),
                playlist_count=data.get("playlist_count") or len(entries),
            )
            return info

        # Vídeo (posiblemente con list= en la URL)
        opts = {**_base_opts(), "skip_download": True, "noplaylist": True}
        data = _with_fallback(opts, lambda variant: _extract(url, variant))
        info.update(
            ok=True,
            kind="video",
            title=data.get("title") or "",
            channel=data.get("uploader") or data.get("channel") or "",
            duration=data.get("duration") or 0,
            thumbnail=_best_thumbnail(data),
            has_playlist=bool(has_list),
        )

        if has_list:
            # Segunda consulta (ligera) para saber cuántos elementos tiene la playlist
            try:
                pl_opts = {
                    **_base_opts(),
                    "extract_flat": "in_playlist",
                    "skip_download": True,
                    "playlist_items": "1",
                }
                playlist = _with_fallback(pl_opts, lambda variant: _extract(url, variant))
                if playlist.get("_type") == "playlist":
                    info["playlist_count"] = playlist.get("playlist_count") or len(
                        playlist.get("entries") or []
                    )
                    if info["playlist_count"] <= 0:
                        info["has_playlist"] = False
                else:
                    info["has_playlist"] = False
            except Exception:  # noqa: BLE001 - si falla, seguimos con el vídeo
                pass

    except Exception as error:  # noqa: BLE001 - se muestra al usuario
        info["error"] = _clean_error(error)
    return info


def download(job, update=None):
    """
    Descarga `job['url']` y convierte a MP3.

    job: dict con url, output_dir, quality ('192'...), embed (bool),
         no_playlist (bool), playlist_total (int) y cancel_event (threading.Event)
    update: callback opcional que recibe dicts con cambios de estado/progreso
    """
    output_dir = Path(job.get("output_dir") or DEFAULT_OUTPUT_DIR)
    output_dir.mkdir(parents=True, exist_ok=True)

    cancel_event = job.get("cancel_event")
    playlist_total = int(job.get("playlist_total") or 0)

    def emit(patch):
        if update is not None:
            update(patch)

    def progress_hook(data):
        if cancel_event is not None and cancel_event.is_set():
            raise yt_dlp.utils.DownloadCancelled("Descarga cancelada por el usuario")
        status = data.get("status")
        info = data.get("info_dict") or {}
        index = info.get("playlist_index") or 0
        total = info.get("n_entries") or info.get("playlist_count") or playlist_total or 0
        if status == "downloading":
            done = data.get("downloaded_bytes") or 0
            size = data.get("total_bytes") or data.get("total_bytes_estimate") or 0
            percent = (done / size * 100) if size else 0
            emit(
                {
                    "status": "downloading",
                    "progress": round(percent, 1),
                    "speed": data.get("speed") or 0,
                    "eta": data.get("eta") or 0,
                    "playlist_index": index,
                    "playlist_total": total,
                }
            )
        elif status == "finished":
            emit(
                {
                    "status": "converting",
                    "progress": 100.0,
                    "speed": 0,
                    "eta": 0,
                    "playlist_index": index,
                    "playlist_total": total,
                }
            )

    def postprocessor_hook(data):
        if cancel_event is not None and cancel_event.is_set():
            raise yt_dlp.utils.DownloadCancelled("Descarga cancelada por el usuario")
        if data.get("status") != "finished":
            return
        info = data.get("info_dict") or {}
        emit(
            {
                "status": "converting",
                "progress": 100.0,
                "speed": 0,
                "eta": 0,
                "playlist_index": info.get("playlist_index") or 0,
                "playlist_total": info.get("n_entries") or playlist_total or 0,
            }
        )

    template = "%(title)s.%(ext)s"
    if not job.get("no_playlist") and playlist_total > 1:
        # En playlists, numerar los archivos para conservar el orden
        template = "%(playlist_index&{} - |)s%(title)s.%(ext)s"

    opts = {
        **_base_opts(),
        "format": "bestaudio/best",
        "outtmpl": str(output_dir / template),
        "windowsfilenames": True,
        "ignoreerrors": False if job.get("no_playlist") else "only_download",
        "noplaylist": bool(job.get("no_playlist")),
        "progress_hooks": [progress_hook],
        "postprocessor_hooks": [postprocessor_hook],
        "postprocessors": [
            {
                "key": "FFmpegExtractAudio",
                "preferredcodec": "mp3",
                "preferredquality": str(job.get("quality") or "192"),
            }
        ],
    }

    if job.get("embed"):
        opts["writethumbnail"] = True
        opts["postprocessors"] += [
            {"key": "FFmpegMetadata", "add_metadata": True},
            {"key": "EmbedThumbnail", "already_have_thumbnail": False},
        ]

    def download_once(attempt_opts):
        with yt_dlp.YoutubeDL(attempt_opts) as ydl:
            return ydl.download([job["url"]])

    retcode = _with_fallback(opts, download_once)
    if retcode:
        raise RuntimeError("yt-dlp no pudo completar la descarga")

    return {"filepath": str(output_dir)}
