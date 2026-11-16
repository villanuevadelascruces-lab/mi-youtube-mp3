#!/usr/bin/env python3
"""
YT2MP3 - Servidor local de la interfaz web.

Arranca un servidor HTTP privado (127.0.0.1), abre el navegador y deja que la
interfaz de `web/` controle las descargas. No usa dependencias externas: solo
la biblioteca estándar de Python y yt-dlp (más ffmpeg para convertir a MP3).

Uso:  python app.py [--no-browser] [--port 8123]
"""

import argparse
import json
import mimetypes
import os
import re
import socket
import sys
import threading
import time
import traceback
import webbrowser
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import unquote, urlparse

import yt_dlp

import downloader

VERSION = "1.1"
HOST = "127.0.0.1"
DEFAULT_PORT = 8123
PORT_ATTEMPTS = 10
MAX_PARALLEL = 4
MAX_URLS = 25

BASE_DIR = Path(__file__).resolve().parent
WEB_DIR = BASE_DIR / "web"
CONFIG_PATH = BASE_DIR / "config.json"
LOG_PATH = BASE_DIR / "yt2mp3.log"

DEFAULT_OUTPUT_DIR = BASE_DIR / "Música descargada"
DEFAULT_SETTINGS = {
    "output_dir": str(DEFAULT_OUTPUT_DIR),
    "quality": "192",
    "embed": True,
}

ACTIVE_STATUSES = {"downloading", "converting"}
ENDED_STATUSES = {"done", "error", "cancelled"}

# ---------------------------------------------------------------------------
# Registro en archivo (pythonw.exe no tiene consola donde escribir)
# ---------------------------------------------------------------------------


def log(message):
    try:
        stamp = time.strftime("%Y-%m-%d %H:%M:%S")
        with open(LOG_PATH, "a", encoding="utf-8") as handle:
            handle.write(f"[{stamp}] {message}\n")
    except OSError:
        pass


# ---------------------------------------------------------------------------
# Utilidades
# ---------------------------------------------------------------------------


def clean_error(error):
    """Convierte una excepción de yt-dlp en un mensaje corto para la interfaz."""
    text = str(error).strip() or error.__class__.__name__
    text = re.sub(r"^ERROR:\s*", "", text)
    text = re.sub(r"\x1b\[[0-9;]*m", "", text)
    first = text.splitlines()[0].strip()
    if "Sign in to confirm" in first or "not a bot" in first.lower():
        return (
            "YouTube ha pedido verificación (no eres un bot). Prueba otra vez "
            "en unos minutos; si sigue igual, coloca un cookies.txt junto a la app."
        )
    if "Private video" in first:
        return "El vídeo es privado."
    if "Video unavailable" in first or "not available" in first:
        return "El vídeo no está disponible."
    return first[:300]


def load_settings():
    settings = dict(DEFAULT_SETTINGS)
    try:
        data = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
        if isinstance(data, dict):
            for key in DEFAULT_SETTINGS:
                if key in data:
                    settings[key] = data[key]
    except (OSError, ValueError):
        pass
    if not settings.get("output_dir"):
        settings["output_dir"] = DEFAULT_SETTINGS["output_dir"]
    if str(settings.get("quality")) not in {"320", "256", "192", "128"}:
        settings["quality"] = DEFAULT_SETTINGS["quality"]
    settings["embed"] = bool(settings.get("embed", True))
    return settings


def save_settings(settings):
    try:
        CONFIG_PATH.write_text(
            json.dumps(settings, ensure_ascii=False, indent=2), encoding="utf-8"
        )
    except OSError as error:
        log(f"No se pudo guardar config.json: {error}")


def folder_size_ok(path):
    try:
        Path(path).mkdir(parents=True, exist_ok=True)
        return True
    except OSError:
        return False


# ---------------------------------------------------------------------------
# Gestor de descargas
# ---------------------------------------------------------------------------


class DownloadManager:
    """Cola de trabajos con hasta MAX_PARALLEL descargas simultáneas."""

    def __init__(self):
        self.lock = threading.Lock()
        self.jobs = {}
        self.order = []
        self.next_id = 1
        self.picker_lock = threading.Lock()

    # -- trabajos ---------------------------------------------------------

    def add(self, item, settings):
        with self.lock:
            job_id = self.next_id
            self.next_id += 1
            job = {
                "id": job_id,
                "url": item.get("url", ""),
                "title": item.get("title") or item.get("url", ""),
                "channel": item.get("channel", ""),
                "duration": int(item.get("duration") or 0),
                "thumbnail": item.get("thumbnail", ""),
                "kind": item.get("kind") or "video",
                "no_playlist": bool(item.get("no_playlist")),
                "playlist_count": int(item.get("playlist_count") or 0),
                "status": "waiting",
                "progress": 0.0,
                "speed": 0,
                "eta": 0,
                "playlist_index": 0,
                "playlist_total": int(item.get("playlist_count") or 0),
                "error": "",
                "quality": str(settings["quality"]),
                "embed": bool(settings["embed"]),
                "output_dir": settings["output_dir"],
                "created_at": time.time(),
                "finished_at": 0,
                "_cancel": threading.Event(),
            }
            self.jobs[job_id] = job
            self.order.append(job_id)
        log(f"Trabajo #{job_id} añadido: {job['title']}")
        self.pump()
        return self.public(job)

    def public(self, job):
        return {key: value for key, value in job.items() if not key.startswith("_")}

    def snapshot(self):
        with self.lock:
            return [self.public(self.jobs[job_id]) for job_id in self.order if job_id in self.jobs]

    def get(self, job_id):
        with self.lock:
            return self.jobs.get(job_id)

    def cancel(self, job_id):
        with self.lock:
            job = self.jobs.get(job_id)
            if not job:
                return False
            if job["status"] == "waiting":
                job["status"] = "cancelled"
                job["finished_at"] = time.time()
                return True
            if job["status"] in ACTIVE_STATUSES:
                job["_cancel"].set()
                return True
            return False

    def retry(self, job_id):
        with self.lock:
            job = self.jobs.get(job_id)
            if not job or job["status"] not in ENDED_STATUSES:
                return False
            job["status"] = "waiting"
            job["error"] = ""
            job["progress"] = 0.0
            job["speed"] = 0
            job["eta"] = 0
            job["playlist_index"] = 0
            job["finished_at"] = 0
            job["_cancel"] = threading.Event()
        self.pump()
        return True

    def remove(self, job_id):
        with self.lock:
            job = self.jobs.get(job_id)
            if not job or job["status"] not in ENDED_STATUSES:
                return False
            del self.jobs[job_id]
            if job_id in self.order:
                self.order.remove(job_id)
            return True

    def clear_ended(self):
        with self.lock:
            for job_id in list(self.order):
                job = self.jobs.get(job_id)
                if job and job["status"] in ENDED_STATUSES:
                    del self.jobs[job_id]
                    self.order.remove(job_id)

    # -- ejecución --------------------------------------------------------

    def pump(self):
        """Arranca trabajos en espera mientras haya hueco libre."""
        with self.lock:
            active = sum(1 for job in self.jobs.values() if job["status"] in ACTIVE_STATUSES)
            slots = MAX_PARALLEL - active
            to_start = []
            if slots > 0:
                for job_id in self.order:
                    job = self.jobs.get(job_id)
                    if job and job["status"] == "waiting":
                        job["status"] = "downloading"
                        to_start.append(job_id)
                        slots -= 1
                        if slots <= 0:
                            break
        for job_id in to_start:
            threading.Thread(target=self._run, args=(job_id,), daemon=True).start()

    def _update(self, job, patch):
        with self.lock:
            # Ignorar actualizaciones de un trabajo ya cancelado
            if job["_cancel"].is_set() and patch.get("status") in {"downloading", "converting"}:
                return
            job.update(patch)
            if job["status"] in ACTIVE_STATUSES and job["playlist_total"] > 1:
                index = max(1, job.get("playlist_index") or 1)
                total = job["playlist_total"]
                overall = None
                if patch.get("status") == "downloading":
                    part = (patch.get("progress") or 0) / 100
                    overall = ((index - 1) + part) / total * 100
                elif patch.get("status") == "converting":
                    overall = index / total * 100
                if overall is not None:
                    job["progress"] = round(min(99.0, overall), 1)

    def _run(self, job_id):
        job = self.get(job_id)
        if not job:
            return
        cancel = job["_cancel"]
        started = time.time()
        log(f"Trabajo #{job_id} iniciado: {job['title']}")
        try:
            if cancel.is_set():
                raise downloader.CancelledError()
            downloader.download(
                {
                    "url": job["url"],
                    "output_dir": job["output_dir"],
                    "quality": job["quality"],
                    "embed": job["embed"],
                    "no_playlist": job["no_playlist"],
                    "playlist_total": job["playlist_total"],
                    "cancel_event": cancel,
                },
                update=lambda patch: self._update(job, patch),
            )
            with self.lock:
                job["status"] = "done"
                job["progress"] = 100.0
                job["speed"] = 0
                job["eta"] = 0
                job["finished_at"] = time.time()
            log(f"Trabajo #{job_id} completado en {time.time() - started:.1f}s")
        except (downloader.CancelledError, yt_dlp.utils.DownloadCancelled):
            with self.lock:
                job["status"] = "cancelled"
                job["speed"] = 0
                job["eta"] = 0
                job["finished_at"] = time.time()
            log(f"Trabajo #{job_id} cancelado por el usuario")
        except Exception as error:  # noqa: BLE001 - se muestra al usuario
            message = clean_error(error)
            with self.lock:
                job["status"] = "error"
                job["error"] = message
                job["speed"] = 0
                job["eta"] = 0
                job["finished_at"] = time.time()
            log(f"Trabajo #{job_id} con error: {message}\n{traceback.format_exc()}")
        finally:
            self.pump()

    # -- carpetas ---------------------------------------------------------

    def pick_folder(self, initial):
        """Abre el selector nativo de carpetas de Windows."""
        if not self.picker_lock.acquire(blocking=False):
            return ""
        try:
            import tkinter as tk
            from tkinter import filedialog

            root = tk.Tk()
            root.withdraw()
            root.attributes("-topmost", True)
            try:
                selected = filedialog.askdirectory(
                    title="Elegir carpeta de salida",
                    initialdir=initial if Path(initial).is_dir() else str(BASE_DIR),
                )
            finally:
                root.destroy()
            return selected or ""
        except Exception as error:  # noqa: BLE001
            log(f"No se pudo abrir el selector de carpetas: {error}")
            return ""
        finally:
            self.picker_lock.release()


MANAGER = DownloadManager()
SETTINGS = load_settings()
MUTEX = None


# ---------------------------------------------------------------------------
# Servidor HTTP
# ---------------------------------------------------------------------------


class Server(ThreadingHTTPServer):
    # En Windows, allow_reuse_address permitiría que dos procesos escuchen el
    # mismo puerto: lo desactivamos y usamos un mutex para una única instancia.
    allow_reuse_address = False
    daemon_threads = True


class Handler(BaseHTTPRequestHandler):
    server_version = f"YT2MP3/{VERSION}"
    protocol_version = "HTTP/1.1"

    # Silenciar el log de cada petición en consola
    def log_message(self, *args):
        pass

    # -- helpers ----------------------------------------------------------

    def send_json(self, payload, status=HTTPStatus.OK):
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def send_bytes(self, body, content_type, status=HTTPStatus.OK):
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def read_json(self):
        try:
            length = int(self.headers.get("Content-Length") or 0)
        except ValueError:
            length = 0
        if length <= 0:
            return {}
        raw = self.rfile.read(min(length, 2_000_000))
        try:
            data = json.loads(raw.decode("utf-8"))
            return data if isinstance(data, dict) else {}
        except (ValueError, UnicodeDecodeError):
            return {}

    def origin_allowed(self):
        """Solo acepta peticiones de la propia interfaz (evita CSRF desde webs)."""
        origin = self.headers.get("Origin")
        if not origin:
            return True
        port = self.server.server_address[1]
        return origin in {
            f"http://127.0.0.1:{port}",
            f"http://localhost:{port}",
        }

    def static_file(self, relative):
        target = (WEB_DIR / relative).resolve()
        try:
            target.relative_to(WEB_DIR.resolve())
        except ValueError:
            self.send_json({"error": "Ruta no permitida"}, HTTPStatus.BAD_REQUEST)
            return
        if not target.is_file():
            self.send_json({"error": "No encontrado"}, HTTPStatus.NOT_FOUND)
            return
        mime, _ = mimetypes.guess_type(str(target))
        self.send_bytes(target.read_bytes(), mime or "application/octet-stream")

    # -- rutas ------------------------------------------------------------

    def do_GET(self):
        path = urlparse(self.path).path
        if path in ("/", "/index.html"):
            self.static_file("index.html")
        elif path == "/favicon.ico":
            icon = BASE_DIR / "icon.ico"
            if icon.is_file():
                self.send_bytes(icon.read_bytes(), "image/x-icon")
            else:
                self.send_json({}, HTTPStatus.NOT_FOUND)
        elif path == "/api/health":
            self.send_json({"app": "yt2mp3", "version": VERSION})
        elif path == "/api/state":
            self.send_json(
                {
                    "app": "yt2mp3",
                    "version": VERSION,
                    "jobs": MANAGER.snapshot(),
                    "settings": SETTINGS,
                    "ffmpeg": downloader.ffmpeg_available(),
                    "max_parallel": MAX_PARALLEL,
                }
            )
        elif path == "/api/log":
            try:
                text = LOG_PATH.read_text(encoding="utf-8", errors="replace")[-8000:]
            except OSError:
                text = ""
            self.send_bytes(text.encode("utf-8"), "text/plain; charset=utf-8")
        else:
            self.static_file(unquote(path.lstrip("/")))

    def do_POST(self):
        path = urlparse(self.path).path
        if not self.origin_allowed():
            self.send_json({"error": "Origen no permitido"}, HTTPStatus.FORBIDDEN)
            return
        data = self.read_json()

        if path == "/api/analyze":
            urls = [u for u in (data.get("urls") or []) if isinstance(u, str)][:MAX_URLS]
            if not urls:
                self.send_json({"error": "No hay enlaces"}, HTTPStatus.BAD_REQUEST)
                return
            self.send_json({"items": analyze_many(urls)})

        elif path == "/api/queue":
            items = data.get("items") or []
            added = [MANAGER.add(item, SETTINGS) for item in items if item.get("url")]
            self.send_json({"added": added})

        elif path == "/api/cancel":
            self.send_json({"ok": MANAGER.cancel(int(data.get("id") or 0))})

        elif path == "/api/retry":
            self.send_json({"ok": MANAGER.retry(int(data.get("id") or 0))})

        elif path == "/api/remove":
            self.send_json({"ok": MANAGER.remove(int(data.get("id") or 0))})

        elif path == "/api/clear":
            MANAGER.clear_ended()
            self.send_json({"ok": True})

        elif path == "/api/settings":
            updated = {}
            for key in ("output_dir", "quality", "embed"):
                if key in data:
                    updated[key] = data[key]
            if "output_dir" in updated:
                value = str(updated["output_dir"]).strip().strip('"')
                if value and folder_size_ok(value):
                    SETTINGS["output_dir"] = value
            if "quality" in updated and str(updated["quality"]) in {"320", "256", "192", "128"}:
                SETTINGS["quality"] = str(updated["quality"])
            if "embed" in updated:
                SETTINGS["embed"] = bool(updated["embed"])
            save_settings(SETTINGS)
            self.send_json({"settings": SETTINGS})

        elif path == "/api/pick-folder":
            initial = str(data.get("initial") or SETTINGS["output_dir"])
            selected = MANAGER.pick_folder(initial)
            if selected:
                SETTINGS["output_dir"] = selected
                save_settings(SETTINGS)
            self.send_json({"path": selected, "settings": SETTINGS})

        elif path == "/api/open-folder":
            target = Path(str(data.get("path") or SETTINGS["output_dir"]))
            try:
                target.mkdir(parents=True, exist_ok=True)
                os.startfile(str(target))  # noqa: S606 - app local de Windows
                self.send_json({"ok": True})
            except OSError as error:
                self.send_json({"ok": False, "error": str(error)}, HTTPStatus.BAD_REQUEST)

        elif path == "/api/shutdown":
            self.send_json({"ok": True})
            log("Apagado solicitado desde la interfaz")
            threading.Thread(target=self.server.shutdown, daemon=True).start()

        else:
            self.send_json({"error": "No encontrado"}, HTTPStatus.NOT_FOUND)


# ---------------------------------------------------------------------------
# Análisis de enlaces
# ---------------------------------------------------------------------------


def analyze_many(urls):
    results = [None] * len(urls)

    def work(index, url):
        try:
            results[index] = downloader.analyze_url(url)
        except Exception as error:  # noqa: BLE001
            results[index] = {
                "url": url,
                "ok": False,
                "error": clean_error(error),
            }

    threads = [
        threading.Thread(target=work, args=(index, url), daemon=True)
        for index, url in enumerate(urls)
    ]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()
    return [result for result in results if result]


# ---------------------------------------------------------------------------
# Arranque
# ---------------------------------------------------------------------------


def already_running(port):
    """True si en ese puerto ya responde esta misma aplicación."""
    try:
        with socket.create_connection((HOST, port), timeout=0.4) as sock:
            sock.sendall(
                b"GET /api/health HTTP/1.1\r\nHost: 127.0.0.1\r\nConnection: close\r\n\r\n"
            )
            data = sock.recv(2048)
        return b'"app": "yt2mp3"' in data
    except OSError:
        return False


def find_running_instance():
    for _ in range(10):
        for port in range(DEFAULT_PORT, DEFAULT_PORT + PORT_ATTEMPTS):
            if already_running(port):
                return port
        time.sleep(0.25)
    return None


def acquire_single_instance():
    """
    Evita dos servidores a la vez (doble clic repetido en el icono).

    Devuelve el handle del mutex si somos la primera instancia, o None si ya
    hay otra YT2MP3 en marcha.
    """
    try:
        import ctypes

        kernel32 = ctypes.windll.kernel32
        handle = kernel32.CreateMutexW(None, False, "Local\\YT2MP3_SingleInstance")
        if not handle:
            return True  # sin mutex seguimos adelante
        if kernel32.GetLastError() == 183:  # ERROR_ALREADY_EXISTS
            kernel32.CloseHandle(handle)
            return None
        return handle
    except Exception:  # noqa: BLE001 - en otros sistemas no hace falta
        return True


def serve(port):
    # El registro no debe crecer sin límite
    try:
        if LOG_PATH.exists() and LOG_PATH.stat().st_size > 1_000_000:
            LOG_PATH.write_text("", encoding="utf-8")
    except OSError:
        pass

    httpd = Server((HOST, port), Handler)
    url = f"http://{HOST}:{port}/"
    log(f"Servidor escuchando en {url} (Python {sys.version.split()[0]})")
    print(f"\n  YT2MP3 v{VERSION} en marcha: {url}")
    print("  Cierra esta ventana (o pulsa 'Salir' en la web) para apagar la app.\n")
    if not os.environ.get("YT2MP3_NO_BROWSER"):
        threading.Timer(0.8, lambda: webbrowser.open(url)).start()
    try:
        httpd.serve_forever(poll_interval=0.3)
    except KeyboardInterrupt:
        pass
    finally:
        httpd.server_close()
        log("Servidor detenido")


def main():
    parser = argparse.ArgumentParser(description="YT2MP3 - interfaz web local")
    parser.add_argument("--port", type=int, default=DEFAULT_PORT)
    parser.add_argument("--no-browser", action="store_true", help="No abrir el navegador")
    args = parser.parse_args()

    if args.no_browser:
        os.environ["YT2MP3_NO_BROWSER"] = "1"

    if not WEB_DIR.is_dir():
        print("No se encuentra la carpeta 'web' junto a app.py.")
        return 1

    global MUTEX
    MUTEX = acquire_single_instance()
    if MUTEX is None:
        running = find_running_instance()
        if running:
            url = f"http://{HOST}:{running}/"
            print(f"YT2MP3 ya estaba abierto. Abriendo {url}")
            if not args.no_browser:
                webbrowser.open(url)
            return 0
        print("YT2MP3 ya se está iniciando. Espera unos segundos y vuelve a intentarlo.")
        return 0

    for port in range(args.port, args.port + PORT_ATTEMPTS):
        try:
            serve(port)
            return 0
        except OSError as error:
            log(f"Puerto {port} ocupado: {error}")
    print("No se encontró un puerto libre para arrancar la interfaz.")
    return 1


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception:  # noqa: BLE001
        log("Fallo inesperado:\n" + traceback.format_exc())
        raise
