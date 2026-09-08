from __future__ import annotations

import threading
import time
from dataclasses import dataclass
from typing import Any, Dict, Optional

from .audio import AudioPlayer
from .robot import G1Robot
from .routines import Routine, RoutineStore


class BusyError(RuntimeError):
    pass


@dataclass
class PlaybackStatus:
    state: str = "idle"
    routine_id: Optional[str] = None
    started_at: Optional[float] = None
    error: Optional[str] = None
    motion_id: Optional[str] = None

    def dict(self) -> Dict[str, Any]:
        return vars(self).copy()


class RoutinePlayer:
    def __init__(self, store: RoutineStore, robot: G1Robot, audio: AudioPlayer):
        self.store = store
        self.robot = robot
        self.audio = audio
        self._status = PlaybackStatus()
        self._lock = threading.Lock()
        self._cancel = threading.Event()
        self._pause = threading.Event()
        self._thread: Optional[threading.Thread] = None
        self._robot_active = False

    def status(self) -> Dict[str, Any]:
        with self._lock:
            status = self._status.dict()
        status["robot_connected"] = self.robot.is_initialized
        return status

    def connect_robot(self) -> Dict[str, Any]:
        self.robot.initialize()
        return self.status()

    def play(self, routine: Routine, *, background: bool = True) -> None:
        with self._lock:
            if self._thread is not None and self._thread.is_alive():
                raise BusyError("Another routine is already playing")
            self._cancel.clear()
            self._pause.clear()
            self._robot_active = True
            self._status = PlaybackStatus("playing", routine.id, time.time(), None)
            self._thread = threading.Thread(target=self._run, args=(routine,), daemon=True)
            thread = self._thread
            thread.start()
        if not background:
            thread.join()
            status = self.status()
            if status["state"] == "error":
                raise RuntimeError(status["error"])

    def play_music(self, routine: Routine) -> None:
        if not routine.audio:
            raise RuntimeError(f"Dance '{routine.name}' has no MP3 attached")
        with self._lock:
            if self._thread is not None and self._thread.is_alive():
                raise BusyError("Another routine or song is already playing")
            self._cancel.clear()
            self._pause.clear()
            self._robot_active = False
            self._status = PlaybackStatus("playing", routine.id, time.time(), None)
            self._thread = threading.Thread(target=self._run_music, args=(routine,), daemon=True)
            self._thread.start()

    def play_motion(self, motion_id: str, action_id: int) -> None:
        with self._lock:
            if self._thread is not None and self._thread.is_alive():
                raise BusyError("Another routine or motion is already playing")
            self._cancel.clear()
            self._pause.clear()
            self._robot_active = True
            self._status = PlaybackStatus(
                state="playing", started_at=time.time(), motion_id=motion_id
            )
            self._thread = threading.Thread(
                target=self._run_motion, args=(action_id,), daemon=True
            )
            self._thread.start()

    def stop(self) -> None:
        self._cancel.set()
        self._pause.clear()
        self.audio.stop()
        try:
            self.robot.stop()
        finally:
            with self._lock:
                self._status.state = "stopped"

    def pause(self) -> None:
        with self._lock:
            if self._status.state != "playing":
                raise BusyError("No playing routine to pause")
            self._pause.set()
            self._status.state = "paused"
        self.audio.pause()
        if self._robot_active:
            self.robot.stop()

    def resume(self) -> None:
        with self._lock:
            if self._status.state != "paused":
                raise BusyError("No paused routine to resume")
            self.audio.resume()
            self._status.state = "playing"
            self._pause.clear()

    def reset(self) -> None:
        self._cancel.set()
        self._pause.clear()
        self.audio.stop()
        if self._robot_active:
            self.robot.stop()
        with self._lock:
            self._status = PlaybackStatus()
            self._robot_active = False

    def _wait_while_paused(self) -> float:
        if not self._pause.is_set():
            return 0.0
        began = time.monotonic()
        while self._pause.is_set() and not self._cancel.wait(0.05):
            pass
        return time.monotonic() - began

    def _run(self, routine: Routine) -> None:
        try:
            # DDS/client setup can take noticeable time. Complete it before using
            # the audio launch as the shared start signal.
            self.robot.initialize()
            if routine.audio:
                self.audio.play(self.store.audio_dir / routine.audio)
            start = time.monotonic()
            paused_time = 0.0
            for step in routine.steps:
                while True:
                    paused_time += self._wait_while_paused()
                    if self._cancel.is_set():
                        return
                    delay = float(step["at"]) - (time.monotonic() - start - paused_time)
                    if delay <= 0:
                        break
                    if self._cancel.wait(min(delay, 0.05)):
                        return
                self.robot.execute(step)
            # Keep the routine busy until its song finishes, preventing a second
            # play request from orphaning or overlapping the first audio process.
            while self.audio.is_playing():
                self._wait_while_paused()
                if self._cancel.wait(0.1):
                    return
            with self._lock:
                if not self._cancel.is_set():
                    self._status.state = "complete"
        except Exception as exc:
            self.audio.stop()
            try:
                self.robot.stop()
            except Exception:
                pass
            with self._lock:
                self._status.state = "error"
                self._status.error = str(exc)

    def _run_music(self, routine: Routine) -> None:
        try:
            self.audio.play(self.store.audio_dir / routine.audio)  # type: ignore[arg-type]
            while self.audio.is_playing():
                self._wait_while_paused()
                if self._cancel.wait(0.1):
                    return
            with self._lock:
                if not self._cancel.is_set():
                    self._status.state = "complete"
        except Exception as exc:
            self.audio.stop()
            with self._lock:
                self._status.state = "error"
                self._status.error = str(exc)

    def _run_motion(self, action_id: int) -> None:
        try:
            self.robot.execute({"type": "arm_action", "action_id": action_id})
            with self._lock:
                if not self._cancel.is_set():
                    self._status.state = "complete"
        except Exception as exc:
            with self._lock:
                self._status.state = "error"
                self._status.error = str(exc)
