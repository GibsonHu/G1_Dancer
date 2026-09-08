import json
import tempfile
import unittest
from pathlib import Path

from g1_dancer.routines import RoutineError, RoutineStore


class RoutineStoreTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.store = RoutineStore(Path(self.temp.name))

    def tearDown(self):
        self.temp.cleanup()

    def write(self, name, value):
        (self.store.routines_dir / name).write_text(json.dumps(value), encoding="utf-8")

    def test_valid_routine(self):
        self.write("hello.json", {
            "id": "hello", "name": "Hello", "steps": [
                {"at": 0, "type": "loco", "method": "WaveHand", "args": []},
                {"at": 1, "type": "arm_action", "action_id": 17},
            ]
        })
        routine = self.store.get("hello")
        self.assertEqual(routine.duration, 1.0)

    def test_rejects_traversal_and_arbitrary_method(self):
        with self.assertRaises(RoutineError):
            self.store.get("../bad")
        self.write("bad.json", {
            "id": "bad", "name": "Bad", "steps": [
                {"at": 0, "type": "loco", "method": "__getattribute__", "args": []}
            ]
        })
        with self.assertRaises(RoutineError):
            self.store.get("bad")

    def test_rejects_unordered_steps(self):
        self.write("bad.json", {
            "id": "bad", "name": "Bad", "steps": [
                {"at": 2, "type": "arm_action", "action_id": 17},
                {"at": 1, "type": "arm_action", "action_id": 20},
            ]
        })
        with self.assertRaises(RoutineError):
            self.store.get("bad")


if __name__ == "__main__":
    unittest.main()

