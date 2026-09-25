from __future__ import annotations

import hashlib
import io
import json
import os
import shutil
import tempfile
import mimetypes
import zipfile
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any, Dict, Tuple
from urllib.parse import unquote, urlsplit

from desktop_app import ASSET_DIR, WEB_DIR

from . import bluetooth
from .audio import create_audio_player
from .config import Config, save_config
from .library import Library
from .mimic import MIMIC_PREFIX, MimicCatalog
from .unistore import UniStoreCatalog
from .motions import MOTIONS_BY_ID, public_motions
from .player import BusyError, RoutinePlayer
from .routines import RoutineError, RoutineStore, validate_id


def _json_bytes(value: Any) -> bytes:
    return json.dumps(value, separators=(",", ":")).encode("utf-8")


def make_handler(config: Config, store: RoutineStore, player: RoutinePlayer, config_path: Path | None = None):
    library = Library(store.root)
    mimic_catalog = MimicCatalog(store.root)
    unistore_catalog = UniStoreCatalog(store.root)

    def public_mimic(item):
        result = item.public_dict()
        meta = library.metadata(item)
        result["song_title"] = meta.get("song_title", "")
        result["audio"] = meta.get("audio")
        result["audio_filename"] = meta.get("audio_filename") or (item.name + ".mp3" if meta.get("audio") else None)
        result["video_url"] = "/api/media/mimic/" + item.id + "/video?v=" + str(meta.get("video_revision", "0")) if meta.get("video") else None
        result["media_kind"] = "mimic"
        return result

    def media_key(kind: str, action_id: str) -> str:
        return f"{kind}-{action_id}"

    def media_metadata(kind: str, action_id: str) -> Dict[str, Any]:
        return library.metadata(media_key(kind, action_id))

    def public_motion(item: Dict[str, Any]) -> Dict[str, Any]:
        result = dict(item)
        meta = media_metadata("preset", item["id"])
        result.update(audio=meta.get("audio"), audio_filename=meta.get("audio_filename") or (item["name"] + ".mp3" if meta.get("audio") else None), song_title=meta.get("song_title", ""), media_kind="preset")
        result["video_url"] = "/api/media/preset/" + item["id"] + "/video?v=" + str(meta.get("video_revision", "0")) if meta.get("video") else None
        return result

    def public_unistore(item: Dict[str, Any]) -> Dict[str, Any]:
        result = dict(item)
        meta = media_metadata("unistore", item["id"])
        result.update(audio=meta.get("audio"), audio_filename=meta.get("audio_filename") or (item["name"] + ".mp3" if meta.get("audio") else None), song_title=meta.get("song_title", ""), media_kind="unistore")
        result["video_url"] = "/api/media/unistore/" + item["id"] + "/video?v=" + str(meta.get("video_revision", "0")) if meta.get("video") else None
        return result

    def hidden(kind: str, action_id: str) -> bool:
        key = action_id if kind == "routine" else media_key(kind, action_id)
        return bool(library.metadata(key).get("hidden"))

    def resolve_media(kind: str, action_id: str) -> Dict[str, Any]:
        """Validate that an action exists before allowing a file to be attached."""
        validate_id(action_id)
        if kind == "mimic":
            item = mimic_catalog.get(action_id, player.robot)
            return {"id": item.id, "name": item.name}
        if kind == "preset":
            item = MOTIONS_BY_ID.get(action_id)
            if item is None:
                raise KeyError(action_id)
            return item
        if kind == "unistore":
            return unistore_catalog.get(action_id, player.robot)
        raise ValueError("Unknown action type")

    def audio_path(kind: str, action_id: str) -> Path | None:
        audio = media_metadata(kind, action_id).get("audio")
        return store.audio_dir / audio if isinstance(audio, str) and audio else None

    preferences_path = store.root / "library" / "app_preferences.json"

    def export_app_data() -> bytes:
        """Create a self-contained, portable archive of user-owned app data."""
        output = io.BytesIO()
        with zipfile.ZipFile(output, "w", zipfile.ZIP_DEFLATED) as archive:
            archive.writestr("g1-dancer-export.json", json.dumps({
                "format": 1, "audio_output": config.audio_output,
            }))
            for folder in ("routines", "audio", "library"):
                source = store.root / folder
                if source.exists():
                    for path in source.rglob("*"):
                        if path.is_file():
                            archive.write(path, path.relative_to(store.root).as_posix())
            for filename in ("unistore_apps.json",):
                path = store.root / filename
                if path.is_file():
                    archive.write(path, filename)
        return output.getvalue()

    def import_app_data(data: bytes) -> dict:
        if len(data) < 22 or len(data) > 500 * 1024 * 1024:
            raise ValueError("Backup must be between 22 bytes and 500 MB")
        player.ensure_idle()
        allowed_roots = {"routines", "audio", "library", "unistore_apps.json", "g1-dancer-export.json"}
        staging = Path(tempfile.mkdtemp(prefix="g1-dancer-import-", dir=store.root.parent))
        try:
            with zipfile.ZipFile(io.BytesIO(data)) as archive:
                total = 0
                names = archive.namelist()
                if "g1-dancer-export.json" not in names:
                    raise ValueError("This is not a G1 Dancer backup")
                manifest = json.loads(archive.read("g1-dancer-export.json"))
                if not isinstance(manifest, dict) or manifest.get("format") != 1:
                    raise ValueError("Unsupported G1 Dancer backup format")
                for info in archive.infolist():
                    name = info.filename
                    parts = Path(name).parts
                    if not parts or parts[0] not in allowed_roots or Path(name).is_absolute() or ".." in parts:
                        raise ValueError("Backup contains an unsafe file path")
                    if info.is_dir() or name == "g1-dancer-export.json":
                        continue
                    total += info.file_size
                    if total > 500 * 1024 * 1024:
                        raise ValueError("Backup contents exceed 500 MB")
                    target = staging / name
                    target.parent.mkdir(parents=True, exist_ok=True)
                    with archive.open(info) as source, target.open("wb") as destination:
                        shutil.copyfileobj(source, destination)
            for folder in ("routines", "audio", "library"):
                imported = staging / folder
                if imported.exists():
                    target = store.root / folder
                    shutil.rmtree(target, ignore_errors=True)
                    imported.replace(target)
            cache = staging / "unistore_apps.json"
            if cache.exists():
                cache.replace(store.root / "unistore_apps.json")
            output = manifest.get("audio_output")
            if output in {"browser", "bluetooth", "usb"}:
                player.set_audio(create_audio_player(output, config.audio_player, config.network_interface, config.dry_run))
                config.audio_output = output
                if config_path is not None:
                    save_config(config_path, config)
            return {"audio_output": config.audio_output}
        finally:
            shutil.rmtree(staging, ignore_errors=True)

    def use_bluetooth_output() -> None:
        if config.audio_output == "bluetooth":
            return
        player.set_audio(create_audio_player(
            "bluetooth", config.audio_player, config.network_interface, config.dry_run
        ))
        config.audio_output = "bluetooth"
        if config_path is not None:
            save_config(config_path, config)

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
            self.send_header('Access-Control-Allow-Headers', 'Content-Type, X-G1-Safety-Confirmed, X-Song-Title, X-Original-Filename')
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
                    saved = [dict(library.public(r), kind="routine", category="dance") for r in store.list() if not hidden("routine", r.id)]
                    mimic = [public_mimic(item) for item in mimic_catalog.list(player.robot) if not hidden("mimic", item.id)]
                    self._reply(200, {"routines": saved + mimic})
                elif route == ("api", "status"):
                    status = player.status()
                    # A UniStore app runs outside our player. If it has already
                    # stopped, discard only our stale paused audio record—never
                    # send a robot stop or Damp command.
                    if status["state"] in {"playing", "paused"} and (status.get("routine_id") or "").startswith("unistore-"):
                        app_id = status["routine_id"].removeprefix("unistore-")
                        app = unistore_catalog.get(app_id, player.robot)
                        if app.get("running_status") != "running":
                            player.stop_audio_only()
                            status = player.status()
                    self._reply(200, status)
                elif route == ("api", "unistore"):
                    result = unistore_catalog.discover(player.robot)
                    result["apps"] = [public_unistore(item) for item in result["apps"] if not hidden("unistore", item["id"])]
                    self._reply(200, result)
                elif route == ("api", "motions"):
                    self._reply(200, {"motions": [public_motion(item) for item in public_motions() if not hidden("preset", item["id"])]})
                elif route == ("api", "settings"):
                    self._reply(200, {"audio_output": config.audio_output})
                elif route == ("api", "app-data", "preferences"):
                    self._reply(200, library.metadata("app_preferences"))
                elif route == ("api", "app-data", "export"):
                    self._bytes(export_app_data(), "application/zip")
                elif route == ("api", "bluetooth", "devices"):
                    self._reply(200, {"devices": bluetooth.paired_devices()})
                elif len(route) == 4 and route[:2] == ('api', 'routines') and route[3] == 'artwork':
                    self._bytes(*library.artwork(store.get(route[2])))
                elif len(route) == 4 and route[:2] == ('api', 'routines') and route[3] == 'video':
                    routine = store.get(route[2])
                    meta = library.metadata(routine)
                    if not meta.get("video"):
                        self._reply(404, {"error": "video not found"})
                        return
                    self._bytes((store.audio_dir / meta["video"]).read_bytes(), meta.get("video_mime", "video/mp4"))
                elif len(route) == 4 and route[:2] == ('api', 'routines') and route[3] == 'audio-file':
                    routine = store.get(route[2])
                    if not routine.audio:
                        self._reply(404, {"error": "audio not found"})
                        return
                    self._bytes((store.audio_dir / routine.audio).read_bytes(), "audio/mpeg")
                elif len(route) == 5 and route[:2] == ('api', 'media') and route[4] == 'video':
                    resolve_media(route[2], route[3])
                    meta = media_metadata(route[2], route[3])
                    if not meta.get("video"):
                        self._reply(404, {"error": "video not found"})
                        return
                    self._bytes((store.audio_dir / meta["video"]).read_bytes(), meta.get("video_mime", "video/mp4"))
                elif len(route) == 5 and route[:2] == ('api', 'media') and route[4] == 'audio-file':
                    resolve_media(route[2], route[3])
                    path = audio_path(route[2], route[3])
                    if path is None:
                        self._reply(404, {"error": "audio not found"})
                        return
                    self._bytes(path.read_bytes(), "audio/mpeg")
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
            except (RoutineError, OSError, ValueError, bluetooth.BluetoothError) as exc:
                self._reply(500, {"error": str(exc)})

        def do_POST(self) -> None:
            route = self._route()
            try:
                if len(route) == 4 and route[:2] == ("api", "routines") and route[3] == "play":
                    if self.headers.get("X-G1-Safety-Confirmed") != "YES":
                        self._reply(428, {"error": "clear the area and send X-G1-Safety-Confirmed: YES"})
                        return
                    if route[2].startswith(MIMIC_PREFIX):
                        motion = mimic_catalog.get(route[2], player.robot)
                        player.play_mimic_motion(motion.id, motion.motion_id, motion.duration,
                                                 audio_path("mimic", motion.id))
                    else:
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
                    player.play_motion(motion["id"], motion["action_id"],
                                       audio_path("preset", motion["id"]))
                    self._reply(202, player.status())
                elif len(route) == 4 and route[:2] == ("api", "routines") and route[3] == "music":
                    routine = store.get(route[2])
                    player.play_music(routine)
                    self._reply(202, player.status())
                elif len(route) == 5 and route[:2] == ("api", "media") and route[4] == "music":
                    item = resolve_media(route[2], route[3])
                    path = audio_path(route[2], route[3])
                    if path is None:
                        raise RuntimeError(f"Action '{item.get('name', route[3])}' has no MP3 attached")
                    player.play_audio(media_key(route[2], route[3]), path)
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
                elif route == ("api", "robot", "walk-run"):
                    if self.headers.get("X-G1-Safety-Confirmed") != "YES":
                        self._reply(428, {"error": "clear the area and send X-G1-Safety-Confirmed: YES"})
                        return
                    player.walk_run()
                    self._reply(200, player.status())
                elif route == ("api", "robot", "run-mode"):
                    if self.headers.get("X-G1-Safety-Confirmed") != "YES":
                        self._reply(428, {"error": "clear the area and send X-G1-Safety-Confirmed: YES"})
                        return
                    player.run_mode()
                    self._reply(200, player.status())
                elif route == ("api", "robot", "ready-mode"):
                    if self.headers.get("X-G1-Safety-Confirmed") != "YES":
                        self._reply(428, {"error": "clear the area and send X-G1-Safety-Confirmed: YES"})
                        return
                    player.ready_mode()
                    self._reply(200, player.status())
                elif route == ("api", "robot", "damped-mode"):
                    player.damped_mode()
                    self._reply(200, player.status())
                elif route == ("api", "robot", "emergency-stop"):
                    player.emergency_stop()
                    self._reply(200, player.status())
                elif len(route) == 4 and route[:2] == ("api", "unistore") and route[3] == "play":
                    if self.headers.get("X-G1-Safety-Confirmed") != "YES":
                        self._reply(428, {"error": "clear the area and send X-G1-Safety-Confirmed: YES"})
                        return
                    app = unistore_catalog.get(route[2], player.robot)
                    if not app.get("instance_id"):
                        self._reply(400, {"error": "UniStore app instance is unavailable"})
                        return
                    path = audio_path("unistore", route[2])
                    if path is not None:
                        # Do this check before the robot receives the app action;
                        # otherwise a busy audio player could start a dance silently.
                        player.ensure_idle()
                    result = player.robot.run_unistore_action(app["instance_id"])
                    if path is not None:
                        # Browser audio is owned by the browser; track the
                        # external dance so its browser MP3 stops with it.
                        if config.audio_output == "browser":
                            player.track_external_action(media_key("unistore", route[2]))
                        else:
                            player.play_audio(media_key("unistore", route[2]), path)
                    self._reply(202, {"app": app, "result": result, "playback": player.status()})
                elif route == ("api", "bluetooth", "scan"):
                    self._reply(200, {"devices": bluetooth.scan(10)})
                elif len(route) == 4 and route[:3] == ("api", "bluetooth", "pair"):
                    device = bluetooth.pair(route[3])
                    use_bluetooth_output()
                    self._reply(200, {"device": device, "devices": bluetooth.paired_devices()})
                elif len(route) == 4 and route[:3] == ("api", "bluetooth", "connect"):
                    device = bluetooth.connect(route[3])
                    use_bluetooth_output()
                    self._reply(200, {"device": device, "devices": bluetooth.paired_devices()})
                else:
                    self._reply(404, {"error": "not found"})
            except KeyError:
                self._reply(404, {"error": "routine not found"})
            except BusyError as exc:
                self._reply(409, {"error": str(exc)})
            except (RoutineError, RuntimeError, bluetooth.BluetoothError) as exc:
                self._reply(400, {"error": str(exc)})

        def do_PUT(self) -> None:
            route = self._route()
            if route == ("api", "app-data", "preferences"):
                try:
                    length = int(self.headers.get("Content-Length", "0"))
                    if not 2 <= length <= 20_000:
                        raise ValueError("Invalid preferences")
                    value = json.loads(self.rfile.read(length))
                    if not isinstance(value, dict):
                        raise ValueError("Invalid preferences")
                    preferences = {key: value.get(key, []) for key in ("library_favorites", "unistore_favorites")}
                    if any(not isinstance(items, list) or len(items) > 500 or any(not isinstance(item, str) or len(item) > 200 for item in items) for items in preferences.values()):
                        raise ValueError("Invalid favourites")
                    library.update("app_preferences", **preferences)
                    self._reply(200, preferences)
                except (ValueError, OSError, json.JSONDecodeError) as exc:
                    self._reply(400, {"error": str(exc)})
                return
            if route == ("api", "app-data", "import"):
                try:
                    length = int(self.headers.get("Content-Length", "0"))
                    if length < 22 or length > 500 * 1024 * 1024:
                        raise ValueError("Backup must be between 22 bytes and 500 MB")
                    self.connection.settimeout(120)
                    result = import_app_data(self.rfile.read(length))
                    self._reply(200, result)
                except (ValueError, OSError, zipfile.BadZipFile, BusyError, json.JSONDecodeError) as exc:
                    self._reply(400, {"error": str(exc)})
                return
            if len(route) == 5 and route[:2] == ("api", "media") and route[4] == "title":
                try:
                    length = int(self.headers.get("Content-Length", "0"))
                    if not 2 <= length <= 1000:
                        raise ValueError("Invalid display-name request")
                    value = json.loads(self.rfile.read(length))
                    title = value.get("title") if isinstance(value, dict) else None
                    if not isinstance(title, str) or not title.strip() or len(title.strip()) > 100:
                        raise ValueError("Display name must be between 1 and 100 characters")
                    resolve_media(route[2], route[3])
                    library.update(media_key(route[2], route[3]), song_title=title.strip())
                    self._reply(200, {"action": {"id": route[3], "kind": route[2], "song_title": title.strip()}})
                except KeyError:
                    self._reply(404, {"error": "action not found"})
                except (ValueError, OSError, json.JSONDecodeError) as exc:
                    self._reply(400, {"error": str(exc)})
                return
            if len(route) == 4 and route[:2] == ("api", "routines") and route[3] == "title":
                try:
                    length = int(self.headers.get("Content-Length", "0"))
                    if not 2 <= length <= 1000:
                        raise ValueError("Invalid display-name request")
                    value = json.loads(self.rfile.read(length))
                    title = value.get("title") if isinstance(value, dict) else None
                    if not isinstance(title, str) or not title.strip() or len(title.strip()) > 100:
                        raise ValueError("Display name must be between 1 and 100 characters")
                    if route[2].startswith(MIMIC_PREFIX):
                        item = mimic_catalog.get(route[2], player.robot)
                        library.update(item, song_title=title.strip())
                        result = public_mimic(item)
                    else:
                        item = store.get(route[2])
                        library.update(item, song_title=title.strip())
                        result = dict(library.public(item), kind="routine", category="dance")
                    self._reply(200, {"routine": result})
                except KeyError:
                    self._reply(404, {"error": "routine not found"})
                except (ValueError, OSError, json.JSONDecodeError) as exc:
                    self._reply(400, {"error": str(exc)})
                return
            if route == ("api", "settings", "audio-output"):
                try:
                    length = int(self.headers.get("Content-Length", "0"))
                    if not 2 <= length <= 100:
                        raise ValueError("Invalid audio output request")
                    value = json.loads(self.rfile.read(length))
                    output = value.get("audio_output") if isinstance(value, dict) else None
                    if output not in {"bluetooth", "usb", "browser"}:
                        raise ValueError("audio_output must be bluetooth, usb, or browser")
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
            asset = route[-1] if route else ""
            generic_media = len(route) == 5 and route[:2] == ("api", "media") and asset in {"audio", "video"}
            routine_media = len(route) == 4 and route[:2] == ("api", "routines") and asset in {"audio", "video"}
            if not generic_media and not routine_media:
                self._reply(404, {"error": "not found"})
                return
            temporary: Path | None = None
            try:
                if generic_media:
                    kind, action_id = route[2], route[3]
                    action = resolve_media(kind, action_id)
                    extension = ".mp3" if asset == "audio" else (".webm" if self.headers.get("Content-Type", "").split(";", 1)[0] == "video/webm" else ".mp4")
                    filename = media_key(kind, action_id) + extension
                else:
                    action_id = route[2]
                    validate_id(action_id)
                    action = store.get(action_id)
                    kind = "routine"
                    extension = ".mp3" if asset == "audio" else (".webm" if self.headers.get("Content-Type", "").split(";", 1)[0] == "video/webm" else ".mp4")
                    filename = f"{action_id}{extension}"
                length_text = self.headers.get("Content-Length")
                if not length_text or not length_text.isdigit():
                    raise ValueError("Content-Length is required")
                length = int(length_text)
                maximum = config.max_upload_mb * 1024 * 1024
                if length < 4 or length > maximum:
                    raise ValueError(f"{asset.upper()} must be between 4 bytes and {config.max_upload_mb} MB")
                fd, temp_name = tempfile.mkstemp(prefix=f".{filename}-", dir=store.audio_dir)
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
                            first = chunk[:32]
                        output.write(chunk)
                        digest.update(chunk)
                        remaining -= len(chunk)
                    output.flush()
                    os.fsync(output.fileno())
                if asset == "audio" and not (first.startswith(b"ID3") or (len(first) >= 2 and first[0] == 0xFF and first[1] & 0xE0 == 0xE0)):
                    raise ValueError("File does not look like an MP3")
                if asset == "video" and not (first.startswith(b"\x1aE\xdf\xa3") or b"ftyp" in first):
                    raise ValueError("Choose an MP4 or WebM video")
                temporary.replace(store.audio_dir / filename)
                temporary = None
                if asset == "video":
                    values = {"video": filename, "video_mime": "video/webm" if extension == ".webm" else "video/mp4", "video_revision": digest.hexdigest()}
                    if generic_media:
                        library.update(media_key(kind, action_id), **values)
                        self._reply(201, {"action": {"id": action_id, "kind": kind, "video": filename}, "sha256": digest.hexdigest()})
                    else:
                        library.update(action, **values)
                        self._reply(201, {"routine": library.public(action), "sha256": digest.hexdigest()})
                else:
                    if generic_media:
                        original_name = unquote(self.headers.get("X-Original-Filename", "")).strip()
                        if not original_name or Path(original_name).name != original_name or not original_name.lower().endswith(".mp3"):
                            original_name = filename
                        library.update(media_key(kind, action_id), audio=filename, audio_filename=original_name)
                        self._reply(201, {"action": {"id": action_id, "kind": kind, "audio": filename}, "sha256": digest.hexdigest()})
                    else:
                        routine = store.attach_audio(action_id, filename)
                        original_name = unquote(self.headers.get("X-Original-Filename", "")).strip()
                        if not original_name or Path(original_name).name != original_name or not original_name.lower().endswith(".mp3"):
                            original_name = filename
                        library.update(routine, audio=filename, audio_filename=original_name)
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
                if len(route) == 5 and route[:2] == ("api", "library"):
                    kind, action_id = route[2], route[3]
                    if route[4] != "hide":
                        self._reply(404, {"error": "not found"})
                        return
                    if kind == "routine":
                        store.get(action_id)
                        key = action_id
                    else:
                        resolve_media(kind, action_id)
                        key = media_key(kind, action_id)
                    library.update(key, hidden=True)
                    self._reply(200, {"id": action_id, "kind": kind, "hidden": True})
                elif len(route) == 4 and route[:2] == ("api", "routines") and route[3] == "audio":
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
