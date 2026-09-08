import json
import tempfile
import unittest
from pathlib import Path

from g1_dancer.audio import AudioPlayer
from g1_dancer.player import RoutinePlayer
from g1_dancer.robot import G1Robot
from g1_dancer.routines import RoutineStore


class PlayerTests(unittest.TestCase):
    def test_dry_run_executes_in_order(self):
        with tempfile.TemporaryDirectory() as directory:
            store = RoutineStore(Path(directory))
            path = store.routines_dir / "test.json"
            steps = [
                {"at": 0, "type": "arm_action", "action_id": 17},
                {"at": 0, "type": "loco", "method": "WaveHand", "args": []},
            ]
            path.write_text(json.dumps({"id": "test", "name": "Test", "steps": steps}))
            robot = G1Robot("unused", dry_run=True)
            player = RoutinePlayer(store, robot, AudioPlayer(dry_run=True))
            player.play(store.get("test"), background=False)
            self.assertEqual(player.status()["state"], "complete")
            self.assertEqual(robot.log, steps)

    def test_music_only_does_not_initialize_or_move_robot(self):
        with tempfile.TemporaryDirectory() as directory:
            store = RoutineStore(Path(directory))
            (store.audio_dir / "song.mp3").write_bytes(b"ID3fake")
            (store.routines_dir / "music.json").write_text(json.dumps({
                "id": "music", "name": "Music", "audio": "song.mp3",
                "steps": [{"at": 0, "type": "arm_action", "action_id": 17}],
            }))
            robot = G1Robot("unused", dry_run=True)
            player = RoutinePlayer(store, robot, AudioPlayer(dry_run=True))
            player.play_music(store.get("music"))
            player._thread.join(timeout=1)
            self.assertEqual(player.status()["state"], "complete")
            self.assertFalse(robot._initialized)
            self.assertEqual(robot.log, [])

    def test_preset_motion_executes_arm_action(self):
        with tempfile.TemporaryDirectory() as directory:
            store = RoutineStore(Path(directory))
            robot = G1Robot("unused", dry_run=True)
            player = RoutinePlayer(store, robot, AudioPlayer(dry_run=True))
            player.play_motion("high-five", 18)
            player._thread.join(timeout=1)
            self.assertEqual(player.status()["state"], "complete")
            self.assertEqual(player.status()["motion_id"], "high-five")
            self.assertEqual(robot.log, [{"type": "arm_action", "action_id": 18}])


if __name__ == "__main__":
    unittest.main()
