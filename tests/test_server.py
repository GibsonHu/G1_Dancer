import json
import tempfile
import threading
import unittest
from pathlib import Path
from urllib.error import HTTPError
from urllib.request import Request, urlopen

from g1_dancer.audio import AudioPlayer
from g1_dancer.config import Config
from g1_dancer.player import RoutinePlayer
from g1_dancer.robot import G1Robot
from g1_dancer.routines import RoutineStore
from g1_dancer.server import ThreadingHTTPServer, make_handler


class ServerTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        root = Path(self.temp.name)
        self.store = RoutineStore(root)
        (self.store.routines_dir / "test.json").write_text(json.dumps({
            "id": "test", "name": "Test", "audio": None,
            "steps": [{"at": 0.5, "type": "arm_action", "action_id": 17}],
        }))
        config = Config(data_dir=str(root), listen_host="127.0.0.1", listen_port=0, dry_run=True)
        self.player = RoutinePlayer(self.store, G1Robot("unused", True), AudioPlayer(dry_run=True))
        self.server = ThreadingHTTPServer(("127.0.0.1", 0), make_handler(config, self.store, self.player))
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.url = f"http://127.0.0.1:{self.server.server_port}"

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()
        self.temp.cleanup()

    def request(self, method, path, data=None, headers=None):
        base = {}
        base.update(headers or {})
        return urlopen(Request(self.url + path, method=method, data=data, headers=base))

    def test_shared_web_library(self):
        self.assertIn(b'G1 DANCER', self.request('GET', '/').read())
        self.assertIn(b'<svg', self.request('GET', '/api/routines/test/artwork').read())
        response = self.request('OPTIONS', '/api/routines/test/audio', headers={'Origin':'capacitor://localhost'})
        self.assertEqual(response.headers['Access-Control-Allow-Origin'], 'capacitor://localhost')
        response = self.request('GET', '/api/routines', headers={'Origin':'https://untrusted.example'})
        self.assertIsNone(response.headers.get('Access-Control-Allow-Origin'))
        self.request('PUT', '/api/routines/test/audio', b'ID3test', {'X-Song-Title':'My%20song'})
        self.assertEqual(json.load(self.request('GET', '/api/routines'))['routines'][0]['song_title'], 'My song')
        cover = (Path(__file__).parents[1] / 'g1_dancer/assets/app_icon.png').read_bytes()
        self.request('PUT', '/api/routines/test/artwork', cover)
        self.assertEqual(self.request('GET', '/api/routines/test/artwork').read(), cover)
        with self.assertRaises(HTTPError):
            self.request('PUT', '/api/routines/test/artwork', b'not-an-image')

    def test_list_upload_and_play_confirmation(self):
        listing = json.load(urlopen(self.url + "/api/routines"))
        self.assertEqual(listing["routines"][0]["id"], "test")
        self.assertFalse(json.load(self.request("GET", "/api/status"))["robot_connected"])
        connected = json.load(self.request("POST", "/api/robot/connect", b"{}"))
        self.assertTrue(connected["robot_connected"])
        mp3 = b"ID3\x04\x00\x00fake-mp3"
        uploaded = json.load(self.request("PUT", "/api/routines/test/audio", mp3))
        self.assertEqual(uploaded["routine"]["audio"], "test.mp3")
        with self.assertRaises(HTTPError) as caught:
            self.request("POST", "/api/routines/test/play", b"{}")
        self.assertEqual(caught.exception.code, 428)
        response = self.request("POST", "/api/routines/test/play", b"{}",
                                {"X-G1-Safety-Confirmed": "YES"})
        self.assertEqual(response.status, 202)
        paused = json.load(self.request("POST", "/api/pause", b"{}"))
        self.assertEqual(paused["state"], "paused")
        resumed = json.load(self.request("POST", "/api/resume", b"{}"))
        self.assertEqual(resumed["state"], "playing")
        reset = json.load(self.request("POST", "/api/reset", b"{}"))
        self.assertEqual(reset["state"], "idle")
        music = self.request("POST", "/api/routines/test/music", b"{}")
        self.assertEqual(music.status, 202)

    def test_preset_motion_list_and_safety_confirmation(self):
        motions = json.load(self.request("GET", "/api/motions"))["motions"]
        self.assertEqual(len(motions), 16)
        self.assertIn({"id": "high-wave", "name": "Wave", "icon": "👋"}, motions)
        with self.assertRaises(HTTPError) as caught:
            self.request("POST", "/api/motions/high-wave/play", b"{}")
        self.assertEqual(caught.exception.code, 428)
        response = self.request(
            "POST", "/api/motions/high-wave/play", b"{}",
            {"X-G1-Safety-Confirmed": "YES"},
        )
        self.assertEqual(response.status, 202)
        self.player._thread.join(timeout=1)
        self.assertEqual(self.player.robot.log[-1], {"type": "arm_action", "action_id": 26})


if __name__ == "__main__":
    unittest.main()
