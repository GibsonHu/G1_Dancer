from __future__ import annotations

import json
import os
import re
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Dict


@dataclass
class Config:
    data_dir: str = "~/.local/share/g1-dancer"
    network_interface: str = "eth0"
    listen_host: str = "0.0.0.0"
    listen_port: int = 8787
    dry_run: bool = False
    max_upload_mb: int = 100
    audio_player: str = "auto"

    @property
    def root(self) -> Path:
        return Path(self.data_dir).expanduser().resolve()


def default_config_path() -> Path:
    override = os.environ.get("G1_DANCER_CONFIG")
    if override:
        return Path(override).expanduser()
    directory = Path.home() / ".config" / "g1-dancer"
    yaml_path = directory / "config.yaml"
    legacy_json = directory / "config.json"
    return legacy_json if legacy_json.exists() and not yaml_path.exists() else yaml_path


def load_config(path: Path | None = None) -> Config:
    path = path or default_config_path()
    if not path.exists():
        return Config()
    text = path.read_text(encoding="utf-8")
    raw = _load_yaml(text) if path.suffix.lower() in {".yaml", ".yml"} else json.loads(text)
    if not isinstance(raw, dict):
        raise ValueError("Config root must be an object/mapping")
    # Accept configs created by versions that required API authentication.
    raw.pop("api_token", None)
    known = Config.__dataclass_fields__
    unknown = set(raw) - set(known)
    if unknown:
        raise ValueError(f"Unknown config fields: {', '.join(sorted(unknown))}")
    return Config(**raw)


def initialize_config(path: Path, *, data_dir: str, interface: str, host: str, port: int) -> Config:
    if path.exists():
        raise FileExistsError(f"Config already exists: {path}")
    config = Config(
        data_dir=data_dir,
        network_interface=interface,
        listen_host=host,
        listen_port=port,
    )
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.suffix.lower() in {".yaml", ".yml"}:
        path.write_text(_dump_yaml(asdict(config)), encoding="utf-8")
    else:
        path.write_text(json.dumps(asdict(config), indent=2) + "\n", encoding="utf-8")
    try:
        path.chmod(0o600)
    except OSError:
        pass
    config.root.joinpath("routines").mkdir(parents=True, exist_ok=True)
    config.root.joinpath("audio").mkdir(parents=True, exist_ok=True)
    return config


_YAML_KEY = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")


def _load_yaml(text: str) -> Dict[str, Any]:
    """Read the flat YAML subset used by Config, without an external dependency."""
    result: Dict[str, Any] = {}
    for number, original in enumerate(text.splitlines(), 1):
        line = original.strip()
        if not line or line.startswith("---") or line.startswith("#"):
            continue
        if original[:1].isspace() or ":" not in line:
            raise ValueError(f"Unsupported YAML syntax on line {number}; use flat key: value entries")
        key, value = (part.strip() for part in line.split(":", 1))
        if not _YAML_KEY.fullmatch(key) or not value:
            raise ValueError(f"Invalid YAML config entry on line {number}")
        try:
            result[key] = json.loads(value)
        except json.JSONDecodeError:
            result[key] = value
    return result


def _dump_yaml(values: Dict[str, Any]) -> str:
    lines = ["# G1 Dancer configuration", "---"]
    for key, value in values.items():
        lines.append(f"{key}: {json.dumps(value)}")
    return "\n".join(lines) + "\n"
