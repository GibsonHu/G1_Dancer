from __future__ import annotations

import shutil
import signal
import subprocess
import threading
import time
import uuid
from pathlib import Path
from typing import List, Optional


class AudioError(RuntimeError):
    pass


class AudioPlayer:
    def __init__(self, preference: str = "auto", dry_run: bool = False):
        self.preference = preference
        self.dry_run = dry_run
        self.process: Optional[subprocess.Popen[bytes]] = None

    def command_for(self, path: Path) -> List[str]:
        candidates = {
            "mpv": ["mpv", "--no-video", "--really-quiet", str(path)],
            "ffplay": ["ffplay", "-nodisp", "-autoexit", "-loglevel", "error", str(path)],
            "cvlc": ["cvlc", "--play-and-exit", "--quiet", str(path)],
            "mpg123": ["mpg123", "-q", str(path)],
        }
        names = list(candidates) if self.preference == "auto" else [self.preference]
        for name in names:
            if name in candidates and shutil.which(name):
                return candidates[name]
        raise AudioError("No MP3 player found. Install one of: mpv, ffplay, cvlc, mpg123")

    def play(self, path: Path) -> None:
        if not path.is_file():
            raise AudioError(f"Audio file is missing: {path}")
        if self.dry_run:
            return
        command = self.command_for(path)
        self.process = subprocess.Popen(command, stdin=subprocess.DEVNULL)

    def stop(self) -> None:
        process, self.process = self.process, None
        if process is not None and process.poll() is None:
            process.terminate()
            try:
                process.wait(timeout=2)
            except subprocess.TimeoutExpired:
                process.kill()

    def pause(self) -> None:
        if self.process is not None and self.process.poll() is None:
            self.process.send_signal(signal.SIGSTOP)

    def resume(self) -> None:
        if self.process is not None and self.process.poll() is None:
            self.process.send_signal(signal.SIGCONT)

    def is_playing(self) -> bool:
        return self.process is not None and self.process.poll() is None

    @property
    def error(self) -> Optional[str]:
        return None


class UnitreeAudioPlayer:
    """Stream decoded 16 kHz mono PCM to the G1 AudioClient."""

    def __init__(self, network_interface: str, dry_run: bool = False):
        self.network_interface = network_interface
        self.dry_run = dry_run
        self.process: Optional[subprocess.Popen[bytes]] = None
        self._thread: Optional[threading.Thread] = None
        self._stop = threading.Event()
        self._paused = threading.Event()
        self._lock = threading.Lock()
        self._client = None
        self._error: Optional[str] = None
        self._app_name = "g1-dancer"

    @property
    def error(self) -> Optional[str]:
        return self._error

    def _client_for_stream(self):
        if self._client is not None:
            return self._client
        try:
            from unitree_sdk2py.core.channel import ChannelFactoryInitialize
            from unitree_sdk2py.g1.audio.g1_audio_client import AudioClient
        except ImportError as exc:
            raise AudioError("unitree_sdk2py is not installed; select Bluetooth or USB, or install the Unitree SDK.") from exc
        ChannelFactoryInitialize(0, self.network_interface)
        client = AudioClient()
        client.SetTimeout(10.0)
        client.Init()
        self._client = client
        return client

    def play(self, path: Path) -> None:
        if not path.is_file():
            raise AudioError(f"Audio file is missing: {path}")
        self.stop()
        self._error = None
        self._stop.clear()
        self._paused.clear()
        if self.dry_run:
            return
        if not shutil.which("ffmpeg"):
            raise AudioError("ffmpeg is required to stream music to the G1 speaker")
        client = self._client_for_stream()
        self.process = subprocess.Popen(
            ["ffmpeg", "-v", "error", "-i", str(path), "-f", "s16le", "-acodec", "pcm_s16le", "-ar", "16000", "-ac", "1", "pipe:1"],
            stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
        )
        stream_id = str(uuid.uuid4())
        self._thread = threading.Thread(target=self._stream, args=(client, stream_id), daemon=True)
        self._thread.start()

    def _stream(self, client, stream_id: str) -> None:
        try:
            assert self.process is not None and self.process.stdout is not None
            while not self._stop.is_set():
                while self._paused.is_set() and not self._stop.wait(0.05):
                    pass
                if self._stop.is_set():
                    break
                pcm = self.process.stdout.read(640)  # 20 ms of 16-bit, 16 kHz mono PCM
                if not pcm:
                    break
                result = client.PlayStream(self._app_name, stream_id, pcm)
                if isinstance(result, tuple):
                    result = result[0]
                if result not in (None, 0):
                    raise AudioError(f"G1 speaker rejected audio stream (SDK code {result})")
                time.sleep(len(pcm) / 32000)  # 16 kHz × 16-bit mono
        except Exception as exc:
            if not self._stop.is_set():
                self._error = str(exc)
        finally:
            try:
                client.PlayStop(self._app_name)
            except Exception:
                pass

    def stop(self) -> None:
        self._stop.set()
        self._paused.clear()
        process, self.process = self.process, None
        if process is not None and process.poll() is None:
            process.terminate()
            try:
                process.wait(timeout=2)
            except subprocess.TimeoutExpired:
                process.kill()
        thread, self._thread = self._thread, None
        if thread is not None and thread is not threading.current_thread():
            thread.join(timeout=2)

    def pause(self) -> None:
        self._paused.set()

    def resume(self) -> None:
        self._paused.clear()

    def is_playing(self) -> bool:
        if self.dry_run:
            return False
        return self._thread is not None and self._thread.is_alive()


def create_audio_player(output: str, preference: str, network_interface: str, dry_run: bool = False):
    if output == "unitree":
        return UnitreeAudioPlayer(network_interface, dry_run)
    if output in {"bluetooth", "usb"}:
        return AudioPlayer(preference, dry_run)
    raise AudioError("audio_output must be one of: unitree, bluetooth, usb")
