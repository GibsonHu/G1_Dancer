from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Dict, List

from . import bluetooth
from .audio import AudioPlayer
from .config import Config, default_config_path, initialize_config, load_config
from .player import RoutinePlayer
from .remote import RemoteClient
from .robot import G1Robot
from .routines import RoutineStore
from .server import serve


SAMPLES: List[Dict[str, Any]] = [
    {
        "id": "clap-wave",
        "name": "Clap and Wave",
        "description": "Clap, pause, then wave. Arm action IDs follow Unitree's official action map.",
        "audio": None,
        "steps": [
            {"at": 0.0, "type": "arm_action", "action_id": 17},
            {"at": 4.0, "type": "arm_action", "action_id": 26},
            {"at": 8.0, "type": "arm_action", "action_id": 99},
        ],
    },
    {
        "id": "heart-greeting",
        "name": "Heart Greeting",
        "description": "Wave, make a two-handed heart, and release the arms.",
        "audio": None,
        "steps": [
            {"at": 0.0, "type": "loco", "method": "WaveHand", "args": []},
            {"at": 4.0, "type": "arm_action", "action_id": 20},
            {"at": 8.0, "type": "arm_action", "action_id": 99},
        ],
    },
]


def _print_json(value: Any) -> None:
    print(json.dumps(value, indent=2))


def _seed(store: RoutineStore) -> None:
    for sample in SAMPLES:
        path = store.routines_dir / f"{sample['id']}.json"
        if not path.exists():
            path.write_text(json.dumps(sample, indent=2) + "\n", encoding="utf-8")


def _components(config: Config):
    store = RoutineStore(config.root)
    robot = G1Robot(config.network_interface, config.dry_run)
    audio = AudioPlayer(config.audio_player, config.dry_run)
    return store, RoutinePlayer(store, robot, audio)


def _confirm(args: argparse.Namespace) -> None:
    if not args.yes:
        raise RuntimeError("Refusing to move the robot without --yes (confirm the area is clear and an E-stop is ready)")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="g1-dancer", description="Offline Unitree G1 dance controller")
    parser.add_argument("--config", type=Path, default=default_config_path())
    sub = parser.add_subparsers(dest="command", required=True)

    init = sub.add_parser("init", help="create a local config and sample routines")
    init.add_argument("--data-dir", default=str(Path.home() / ".local" / "share" / "g1-dancer"))
    init.add_argument("--interface", default="eth0", help="Ethernet interface connected to the G1")
    init.add_argument("--host", default="0.0.0.0")
    init.add_argument("--port", default=8787, type=int)

    sub.add_parser("list", help="list routines on this PC")
    run = sub.add_parser("run", help="run a routine on this PC")
    run.add_argument("routine_id")
    run.add_argument("--yes", action="store_true", help="confirm the motion area is clear")
    run.add_argument("--dry-run", action="store_true")
    sub.add_parser("stop", help="stop motion and audio on this PC")
    gui = sub.add_parser("gui", help="open the local-computer remote control GUI")
    gui.add_argument("--url", default="http://10.42.0.1:8787")
    gui.add_argument("--ssh-target", default="unitree@10.42.0.1")
    gui.add_argument("--ssh-port", type=int, default=22)
    gui.add_argument("--classic", action="store_true", help="open the older Tk desktop controller")
    server = sub.add_parser("serve", help="start the authenticated network API")
    server.add_argument("--dry-run", action="store_true")

    speaker = sub.add_parser("speaker", help="manage the PC's Bluetooth speaker")
    speaker_sub = speaker.add_subparsers(dest="speaker_command", required=True)
    scan = speaker_sub.add_parser("scan")
    scan.add_argument("--seconds", type=int, default=10)
    speaker_sub.add_parser("list")
    speaker_sub.add_parser("connected")
    pair = speaker_sub.add_parser("pair")
    pair.add_argument("mac")
    connect = speaker_sub.add_parser("connect")
    connect.add_argument("mac")

    remote = sub.add_parser("remote", help="add MP3s to or play existing development-PC dances")
    remote.add_argument("--url", required=True, help="development-PC API, normally http://10.42.0.1:8787")
    remote_sub = remote.add_subparsers(dest="remote_command", required=True)
    upload = remote_sub.add_parser("add-mp3", help="attach or replace an MP3 on an existing dance")
    upload.add_argument("routine_id", help="ID of a dance already stored on the development PC")
    upload.add_argument("mp3", type=Path, help="local MP3 file to copy to the development PC")
    play = remote_sub.add_parser("play")
    play.add_argument("routine_id", help="ID of a dance already stored on the development PC")
    play.add_argument("--yes", action="store_true", help="confirm the motion area is clear")
    return parser


def main(argv: List[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        if args.command == "init":
            if not (1 <= args.port <= 65535):
                raise ValueError("Port must be between 1 and 65535")
            config = initialize_config(
                args.config, data_dir=args.data_dir, interface=args.interface, host=args.host, port=args.port
            )
            store = RoutineStore(config.root)
            _seed(store)
            print(f"Created {args.config}")
            return 0

        if args.command == "speaker":
            if args.speaker_command == "scan":
                print(bluetooth.scan(args.seconds))
            elif args.speaker_command == "list":
                print("\n".join(bluetooth.paired_devices()) or "No paired devices")
            elif args.speaker_command == "connected":
                print("\n".join(bluetooth.connected_devices()) or "No connected devices")
            elif args.speaker_command == "pair":
                print(bluetooth.pair(args.mac))
            else:
                print(bluetooth.connect(args.mac))
            return 0

        if args.command == "gui":
            if args.classic:
                from .gui import launch
                launch(args.url, args.ssh_target, args.ssh_port)
            else:
                import webbrowser
                webbrowser.open(args.url)
                print(f"G1 DANCER: {args.url}")
            return 0

        if args.command == "remote":
            client = RemoteClient(args.url)
            if args.remote_command == "add-mp3":
                result = client.upload(args.routine_id, args.mp3)
            else:
                _confirm(args)
                result = client.request(
                    "POST", f"/api/routines/{args.routine_id}/play", b"{}", safety_confirmed=True
                )
            _print_json(result)
            return 0

        config = load_config(args.config)
        if getattr(args, "dry_run", False):
            config.dry_run = True
        store, player = _components(config)
        if args.command == "list":
            _print_json({"routines": [routine.public_dict() for routine in store.list()]})
        elif args.command == "run":
            _confirm(args)
            player.play(store.get(args.routine_id), background=False)
            _print_json(player.status())
        elif args.command == "stop":
            player.stop()
            _print_json(player.status())
        elif args.command == "serve":
            serve(config, store, player)
        return 0
    except (Exception, KeyboardInterrupt) as exc:
        if isinstance(exc, KeyboardInterrupt):
            print("Interrupted", file=sys.stderr)
        else:
            print(f"error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
