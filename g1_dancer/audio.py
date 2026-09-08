from __future__ import annotations

import shutil
import signal
import subprocess
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
