from __future__ import annotations

import hashlib
import json
import os
import tempfile
import mimetypes
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any, Dict, Tuple
from urllib.parse import unquote, urlsplit

from desktop_app import ASSET_DIR, WEB_DIR

from .audio import create_audio_player
from .config import Config, save_config
from .library import Library
from .motions import MOTIONS_BY_ID, public_motions
from .player import BusyError, RoutinePlayer
from .routines import RoutineError, RoutineStore, validate_id


def _json_bytes(value: Any) -> bytes:
    return json.dumps(value, separators=(",", ":")).encode("utf-8")


def make_handler(config: Config, store: RoutineStore, player: RoutinePlayer, config_path: Path | None = None):
    library = Library(store.root)
    class Handler(BaseHTTPRequestHandler):
        server_version = "G1Dancer/0.1"

        def end_headers(self):
            origin = self.headers.get('Origin', '')
            if origin in ('capacitor://localhost', 'http://localhost', 'https://localhost'):
                self.send_header('Access-Control-Allow-Origin', origin)
                self.send_header('Vary', 'Origin')
            self.send_header('Cache-Control', 'no-store')
            super().end_headers()

        def do_OPTIONS(self):
            self.send_response(204)
            self.send_header('Access-Control-Allow-Methods', 'GET, POST, PUT, DELETE, OPTIONS')
            self.send_header('Access-Control-Allow-Headers', 'Content-Type, X-G1-Safety-Confirmed, X-Song-Title')
            self.end_headers()

        def _bytes(self, body, mime):
            self.send_response(200)
            self.send_header('Content-Type', mime)
            self.send_header('Content-Length', str(len(body)))
            self.send_header('X-Content-Type-Options', 'nosniff')
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, fmt: str, *args: Any) -> None:
            print(f"{self.client_address[0]} - {fmt % args}")

        def _reply(self, status: int, value: Any) -> None:
            body = _json_bytes(value)
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.send_header("X-Content-Type-Options", "nosniff")
            self.end_headers()
            self.wfile.write(body)

        def _route(self) -> Tuple[str, ...]:
            path = urlsplit(self.path).path
            return tuple(unquote(part) for part in path.strip("/").split("/") if part)

        def do_GET(self) -> None:
            try:
                route = self._route()
                if route == ("api", "health"):
                    self._reply(200, {"ok": True, "dry_run": config.dry_run})
                elif route == ("api", "routines"):
                    self._reply(200, {"routines": [library.public(r) for r in store.list()]})
                elif route == ("api", "status"):
                    self._reply(200, player.status())
                elif route == ("api", "motions"):
                    self._reply(200, {"motions": public_motions()})
                elif route == ("api", "settings"):
                    self._reply(200, {"audio_output": config.audio_output})
                elif len(route) == 4 and route[:2] == ('api', 'routines') and route[3] == 'artwork':
                    self._bytes(*library.artwork(store.get(route[2])))
                elif route == () or (len(route) == 1 and route[0] in ('index.html', 'app.js', 'style.css', 'manifest.webmanifest')):
                    name = route[0] if route else 'index.html'
                    path = WEB_DIR / name
                    self._bytes(path.read_bytes(), mimetypes.guess_type(name)[0] or 'application/octet-stream')
                elif len(route) == 2 and route[0] == 'assets' and route[1] in ('app_icon.png', 'dancer_1_blurred.png'):
                    self._bytes((ASSET_DIR / route[1]).read_bytes(), 'image/png')
                else:
                    self._reply(404, {"error": "not found"})
            except KeyError:
                self._reply(404, {'error': 'routine not found'})
            except (RoutineError, OSError, ValueError) as exc:
                self._reply(500, {"error": str(exc)})

        def do_POST(self) -> None:
            route = self._route()
            try:
                if len(route) == 4 and route[:2] == ("api", "routines") and route[3] == "play":
                    if self.headers.get("X-G1-Safety-Confirmed") != "YES":
                        self._reply(428, {"error": "clear the area and send X-G1-Safety-Confirmed: YES"})
                        return
                    routine = store.get(route[2])
                    player.play(routine)
                    self._reply(202, player.status())
                elif len(route) == 4 and route[:2] == ("api", "motions") and route[3] == "play":
                    if self.headers.get("X-G1-Safety-Confirmed") != "YES":
                        self._reply(428, {"error": "clear the area and send X-G1-Safety-Confirmed: YES"})
                        return
                    motion = MOTIONS_BY_ID.get(route[2])
                    if motion is None:
                        self._reply(404, {"error": "preset motion not found"})
                        return
                    player.play_motion(motion["id"], motion["action_id"])
                    self._reply(202, player.status())
                elif len(route) == 4 and route[:2] == ("api", "routines") and route[3] == "music":
                    routine = store.get(route[2])
                    player.play_music(routine)
                    self._reply(202, player.status())
                elif route == ("api", "stop"):
                    player.stop()
                    self._reply(200, player.status())
                elif route == ("api", "pause"):
                    player.pause()
                    self._reply(200, player.status())
                elif route == ("api", "resume"):
                    player.resume()
                    self._reply(200, player.status())
                elif route == ("api", "reset"):
                    player.reset()
                    self._reply(200, player.status())
                elif route == ("api", "robot", "connect"):
                    player.connect_robot()
                    self._reply(200, player.status())
                else:
                    self._reply(404, {"error": "not found"})
            except KeyError:
                self._reply(404, {"error": "routine not found"})
            except BusyError as exc:
                self._reply(409, {"error": str(exc)})
            except (RoutineError, RuntimeError) as exc:
                self._reply(400, {"error": str(exc)})

        def do_PUT(self) -> None:
            route = self._route()
            if route == ("api", "settings", "audio-output"):
                try:
                    length = int(self.headers.get("Content-Length", "0"))
                    if not 2 <= length <= 100:
                        raise ValueError("Invalid audio output request")
                    value = json.loads(self.rfile.read(length))
                    output = value.get("audio_output") if isinstance(value, dict) else None
                    if output not in {"unitree", "bluetooth", "usb"}:
                        raise ValueError("audio_output must be unitree, bluetooth, or usb")
                    player.set_audio(create_audio_player(
                        output, config.audio_player, config.network_interface, config.dry_run
                    ))
                    config.audio_output = output
                    if config_path is not None:
                        save_config(config_path, config)
                    self._reply(200, {"audio_output": config.audio_output})
                except (ValueError, RuntimeError, OSError, json.JSONDecodeError) as exc:
                    self._reply(400, {"error": str(exc)})
                return
            if len(route) == 4 and route[:2] == ('api', 'routines') and route[3] == 'artwork':
                try:
                    routine = store.get(route[2])
                    length = int(self.headers.get('Content-Length', '0'))
                    if not 4 <= length <= 5 * 1024 * 1024:
                        raise ValueError('Image must be between 4 bytes and 5 MB')
                    self.connection.settimeout(30)
                    data = self.rfile.read(length)
                    if len(data) != length:
                        raise ValueError('Upload ended early')
                    library.save_artwork(routine, data)
                    self._reply(201, {'routine': library.public(routine)})
                except (ValueError, OSError, KeyError) as exc:
                    self._reply(400, {'error': str(exc)})
                return
            if len(route) != 4 or route[:2] != ("api", "routines") or route[3] != "audio":
                self._reply(404, {"error": "not found"})
                return
            temporary: Path | None = None
            try:
                routine_id = route[2]
                validate_id(routine_id)
                store.get(routine_id)
                length_text = self.headers.get("Content-Length")
                if not length_text or not length_text.isdigit():
                    raise ValueError("Content-Length is required")
                length = int(length_text)
                maximum = config.max_upload_mb * 1024 * 1024
                if length < 4 or length > maximum:
                    raise ValueError(f"MP3 must be between 4 bytes and {config.max_upload_mb} MB")
                filename = f"{routine_id}.mp3"
                fd, temp_name = tempfile.mkstemp(prefix=f".{routine_id}-", dir=store.audio_dir)
                temporary = Path(temp_name)
                digest = hashlib.sha256()
                first = b""
                remaining = length
                with os.fdopen(fd, "wb") as output:
                    while remaining:
                        chunk = self.rfile.read(min(1024 * 1024, remaining))
                        if not chunk:
                            raise ValueError("Upload ended early")
                        if not first:
                            first = chunk[:4]
                        output.write(chunk)
                        digest.update(chunk)
                        remaining -= len(chunk)
                    output.flush()
                    os.fsync(output.fileno())
                if not (first.startswith(b"ID3") or (len(first) >= 2 and first[0] == 0xFF and first[1] & 0xE0 == 0xE0)):
                    raise ValueError("File does not look like an MP3")
                temporary.replace(store.audio_dir / filename)
                temporary = None
                routine = store.attach_audio(routine_id, filename)
                title = unquote(self.headers.get('X-Song-Title', routine_id))[:200]
                library.update(routine, song_title=title)
                self._reply(201, {"routine": routine.public_dict(), "sha256": digest.hexdigest()})
            except KeyError:
                self._reply(404, {"error": "routine not found"})
            except (RoutineError, OSError, ValueError) as exc:
                self._reply(400, {"error": str(exc)})
            finally:
                if temporary:
                    temporary.unlink(missing_ok=True)

        def do_DELETE(self) -> None:
            route = self._route()
            try:
                if len(route) == 4 and route[:2] == ("api", "routines") and route[3] == "audio":
                    routine = store.get(route[2])
                    if routine.audio:
                        (store.audio_dir / routine.audio).unlink(missing_ok=True)
                    routine = store.detach_audio(route[2])
                    self._reply(200, {"routine": routine.public_dict()})
                else:
                    self._reply(404, {"error": "not found"})
            except KeyError:
                self._reply(404, {"error": "routine not found"})
            except (RoutineError, OSError) as exc:
                self._reply(400, {"error": str(exc)})

    return Handler


def serve(config: Config, store: RoutineStore, player: RoutinePlayer, config_path: Path | None = None) -> None:
    address = (config.listen_host, config.listen_port)
    server = ThreadingHTTPServer(address, make_handler(config, store, player, config_path))
    print(f"G1 Dancer listening on http://{address[0]}:{address[1]}")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        player.stop()
        server.server_close()
