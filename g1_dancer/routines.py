from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional


ID_RE = re.compile(r"^[a-z0-9][a-z0-9_-]{0,63}$")
LOCO_ACTIONS = {
    "Damp", "HighStand", "LowStand", "ShakeHand", "Squat", "StandUp2Squat",
    "Squat2StandUp", "StopMove", "WaveHand", "ZeroTorque",
}
STEP_TYPES = {"arm_action", "loco"}


class RoutineError(ValueError):
    pass


@dataclass(frozen=True)
class Routine:
    id: str
    name: str
    description: str
    steps: List[Dict[str, Any]]
    audio: Optional[str]
    source: Path

    @property
    def duration(self) -> float:
        return max((float(step["at"]) for step in self.steps), default=0.0)

    def public_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "name": self.name,
            "description": self.description,
            "audio": self.audio,
            "duration": self.duration,
            "steps": len(self.steps),
        }


class RoutineStore:
    def __init__(self, root: Path):
        self.root = root
        self.routines_dir = root / "routines"
        self.audio_dir = root / "audio"
        self.routines_dir.mkdir(parents=True, exist_ok=True)
        self.audio_dir.mkdir(parents=True, exist_ok=True)

    def list(self) -> List[Routine]:
        routines: List[Routine] = []
        for path in sorted(self.routines_dir.glob("*.json")):
            routines.append(self._load_path(path))
        return routines

    def get(self, routine_id: str) -> Routine:
        validate_id(routine_id)
        path = self.routines_dir / f"{routine_id}.json"
        if not path.is_file():
            raise KeyError(routine_id)
        return self._load_path(path)

    def attach_audio(self, routine_id: str, filename: str) -> Routine:
        routine = self.get(routine_id)
        data = json.loads(routine.source.read_text(encoding="utf-8"))
        data["audio"] = filename
        _atomic_json(routine.source, data)
        return self.get(routine_id)

    def detach_audio(self, routine_id: str) -> Routine:
        routine = self.get(routine_id)
        data = json.loads(routine.source.read_text(encoding="utf-8"))
        data["audio"] = None
        _atomic_json(routine.source, data)
        return self.get(routine_id)

    def _load_path(self, path: Path) -> Routine:
        try:
            raw = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise RoutineError(f"Cannot read {path.name}: {exc}") from exc
        if not isinstance(raw, dict):
            raise RoutineError(f"{path.name}: root must be an object")
        routine_id = raw.get("id", path.stem)
        validate_id(routine_id)
        if routine_id != path.stem:
            raise RoutineError(f"{path.name}: id must match filename")
        name = raw.get("name")
        if not isinstance(name, str) or not name.strip():
            raise RoutineError(f"{path.name}: name is required")
        description = raw.get("description", "")
        if not isinstance(description, str):
            raise RoutineError(f"{path.name}: description must be text")
        audio = raw.get("audio")
        if audio is not None:
            if not isinstance(audio, str) or Path(audio).name != audio or not audio.lower().endswith(".mp3"):
                raise RoutineError(f"{path.name}: audio must be a plain .mp3 filename")
        steps = raw.get("steps")
        if not isinstance(steps, list) or not steps:
            raise RoutineError(f"{path.name}: at least one step is required")
        previous = -1.0
        for index, step in enumerate(steps):
            if not isinstance(step, dict):
                raise RoutineError(f"{path.name}: step {index} must be an object")
            at = step.get("at")
            if not isinstance(at, (int, float)) or isinstance(at, bool) or at < 0 or at < previous:
                raise RoutineError(f"{path.name}: step times must be non-negative and ordered")
            previous = float(at)
            kind = step.get("type")
            if kind not in STEP_TYPES:
                raise RoutineError(f"{path.name}: step {index} has unsupported type")
            if kind == "arm_action":
                action_id = step.get("action_id")
                if not isinstance(action_id, int) or isinstance(action_id, bool) or action_id < 0:
                    raise RoutineError(f"{path.name}: arm_action requires a non-negative action_id")
            else:
                method = step.get("method")
                if method not in LOCO_ACTIONS:
                    raise RoutineError(f"{path.name}: loco method {method!r} is not allowed")
                args = step.get("args", [])
                if not isinstance(args, list) or len(args) > 3 or any(not isinstance(v, (bool, int, float)) for v in args):
                    raise RoutineError(f"{path.name}: invalid loco args")
        return Routine(routine_id, name.strip(), description, steps, audio, path)


def validate_id(routine_id: str) -> None:
    if not isinstance(routine_id, str) or not ID_RE.fullmatch(routine_id):
        raise RoutineError("Routine id must use lowercase letters, digits, '-' or '_'")


def _atomic_json(path: Path, data: Dict[str, Any]) -> None:
    temporary = path.with_suffix(".json.tmp")
    temporary.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
    temporary.replace(path)

