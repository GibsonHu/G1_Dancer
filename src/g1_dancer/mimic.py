from __future__ import annotations

import json
import re
import threading
from dataclasses import dataclass
from pathlib import Path
from typing import Any


MIMIC_PREFIX = "mimic-"
_DANCE_IDS = {502, 503, 504, 506, 601, 602, 603, 604, 605}
_RECOVERY_IDS = {401, 402, 403}
_UTILITY_IDS = {101}
_GREETING_WORDS = (
    "hello", "wave", "zhaohu", "huanying", "yingbin", "bow", "shake_hand",
)

# The G1 catalog mixes English with Chinese motion names written as pinyin.
# Keep the robot's raw identifier in the cache and translate only its public
# display name. Keys are normalized after Unitree's filename suffixes are
# removed, making this independent of capitalization and separators.
_ENGLISH_NAMES = {
    "y qishen faceup 001 get up": "Get Up from Face-Up",
    "y qishen faceup 001 lie down": "Lie Down Face-Up",
    "y qishen facedown 002 get up": "Get Up from Face-Down",
    "yskj newbalei 008 v1": "New Ballet",
    "chayao": "Hands on Hips",
    "feiwen": "Blow a Kiss",
    "fuxiongqueren": "Hand-on-Chest Affirmation",
    "jingli": "Salute",
    "naopigu": "Scratch Backside",
    "shuangshoudazhaohu": "Wave with Both Hands",
    "shuangshouhuanying": "Welcome with Both Hands",
    "shuangshoupaijian": "Pat Shoulders with Both Hands",
    "shuangshouwulian": "Cover Face with Both Hands",
    "shuangshouxiongqianfeishou": "Wave Both Hands in Front",
    "shuangshouyouzhi": "Point Right with Both Hands",
    "shuangshouzuozhi": "Point Left with Both Hands",
    "sikao": "Thinking",
    "toudingbixin": "Heart above Head",
    "youqiecai": "Chop to the Right",
    "youshoudazhaohu": "Wave with Right Hand",
    "youshouqianzhi": "Point Forward with Right Hand",
    "ziwojieshao": "Self Introduction",
    "zuoqiecai": "Chop to the Left",
    "zuoshouzhaohu": "Wave with Left Hand",
    "zuoshouzhixiang": "Point with Left Hand",
    "yingbin": "Welcome Guests",
    "yskj jixiewu3 001 xx": "Mechanical Dance 3",
    "yskj woyaofanguoxueshan 001 xx": "I Want to Cross the Snowy Mountain",
}


def _display_name(raw: str) -> str:
    name = re.sub(r"^vq_", "", raw, flags=re.IGNORECASE)
    name = re.sub(r"_[0-9a-f]{8}_G1_50hz$", "", name, flags=re.IGNORECASE)
    name = re.sub(r"_G1_50hz$|(?:\.bvh)?_50hz$|\.bvh$", "", name, flags=re.IGNORECASE)
    normalized = " ".join(re.sub(r"[^a-z0-9]+", " ", name.casefold()).split())
    translated = _ENGLISH_NAMES.get(normalized)
    if translated:
        return translated
    return " ".join(name.replace("-", " ").replace("_", " ").split()).title()


@dataclass(frozen=True)
class MimicMotion:
    motion_id: int
    raw_name: str
    duration: float

    @property
    def id(self) -> str:
        return f"{MIMIC_PREFIX}{self.motion_id}"

    @property
    def category(self) -> str:
        if self.motion_id in _DANCE_IDS:
            return "dance"
        if self.motion_id in _RECOVERY_IDS:
            return "recovery"
        if self.motion_id in _UTILITY_IDS:
            return "utility"
        lowered = self.raw_name.lower()
        if any(word in lowered for word in _GREETING_WORDS):
            return "greeting"
        return "gesture"

    def public_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "name": _display_name(self.raw_name),
            "description": f"Robot-installed mimic motion {self.motion_id}",
            "audio": None,
            "duration": self.duration,
            "steps": 1,
            "song_title": "",
            "artwork_url": None,
            "kind": "mimic",
            "category": self.category,
        }


class MimicCatalog:
    """Discovers robot-resident motions and keeps a cache for offline dry runs."""

    def __init__(self, root: Path):
        self.path = root / "mimic_motions.json"
        self._lock = threading.Lock()
        self._motions = self._read_cache()
        self._queried_robot = False

    def list(self, robot=None) -> list[MimicMotion]:
        with self._lock:
            if robot is not None and not robot.dry_run and not self._queried_robot:
                try:
                    self._motions = self._decode(robot.get_mimic_motions())
                    self._write_cache(self._motions)
                    self._queried_robot = True
                except RuntimeError:
                    # Keep saved routines and the last known robot catalog usable
                    # when the robot is temporarily disconnected.
                    pass
            return list(self._motions)

    def get(self, public_id: str, robot=None) -> MimicMotion:
        if not public_id.startswith(MIMIC_PREFIX):
            raise KeyError(public_id)
        try:
            motion_id = int(public_id[len(MIMIC_PREFIX):])
        except ValueError as exc:
            raise KeyError(public_id) from exc
        for motion in self.list(robot):
            if motion.motion_id == motion_id:
                return motion
        raise KeyError(public_id)

    def _read_cache(self) -> list[MimicMotion]:
        try:
            return self._decode(json.loads(self.path.read_text(encoding="utf-8")))
        except (OSError, ValueError, TypeError, json.JSONDecodeError):
            return []

    def _write_cache(self, motions: list[MimicMotion]) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        value = {
            "motion": {
                str(item.motion_id): {"name": item.raw_name, "duration": item.duration}
                for item in motions
            }
        }
        temporary = self.path.with_suffix(".json.tmp")
        temporary.write_text(json.dumps(value, indent=2) + "\n", encoding="utf-8")
        temporary.replace(self.path)

    @staticmethod
    def _decode(value: Any) -> list[MimicMotion]:
        source = value.get("motion") if isinstance(value, dict) else None
        if not isinstance(source, dict):
            raise ValueError("Robot returned an invalid mimic-motion catalog")
        result = []
        for key, details in source.items():
            if not str(key).isdigit() or not isinstance(details, dict):
                continue
            motion_id = int(key)
            name, duration = details.get("name"), details.get("duration")
            if not 0 <= motion_id <= 999 or not isinstance(name, str) or not name:
                continue
            if not isinstance(duration, (int, float)) or isinstance(duration, bool) or duration < 0:
                continue
            result.append(MimicMotion(motion_id, name, float(duration)))
        return sorted(result, key=lambda item: item.motion_id)
