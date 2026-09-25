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
        (root / "mimic_motions.json").write_text(json.dumps({
            "motion": {"502": {"name": "vq_POPPING1_G1_50hz", "duration": 0}},
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
        page = self.request('GET', '/').read()
        self.assertIn(b'G1 DANCER', page)
        self.assertIn(b'Motion Library', page)
        self.assertNotIn(b'UniStore Library', page)
        self.assertIn(b'Run Mode', page)
        self.assertNotIn(b'data-dance-filter="recovery"', page)
        self.assertNotIn(b'data-dance-filter="utility"', page)
        self.assertIn(b'data-dance-filter="martial-art"', page)
        self.assertIn(b'data-utility-filter="recovery"', page)
        self.assertIn(b'data-utility-filter="utility"', page)
        self.assertLess(page.index(b'id="motion-library"'), page.index(b'id="utility-library"'))
        self.assertIn(b'data-motion-filter="preset"', page)
        self.assertNotIn(b'id="motion-list"', page)
        self.assertIn(b'<svg', self.request('GET', '/api/routines/test/artwork').read())
        response = self.request('OPTIONS', '/api/routines/test/audio', headers={'Origin':'capacitor://localhost'})
        self.assertEqual(response.headers['Access-Control-Allow-Origin'], 'capacitor://localhost')

        response = self.request('GET', '/api/routines', headers={'Origin':'https://untrusted.example'})
        self.assertIsNone(response.headers.get('Access-Control-Allow-Origin'))
        self.request('PUT', '/api/routines/test/audio', b'ID3test', {'X-Song-Title':'My%20song'})
        self.assertEqual(json.load(self.request('GET', '/api/routines'))['routines'][0]['song_title'], '')
        cover = (Path(__file__).parents[1] / 'desktop_app/assets/app_icon.png').read_bytes()
        self.request('PUT', '/api/routines/test/artwork', cover)
        self.assertEqual(self.request('GET', '/api/routines/test/artwork').read(), cover)
        with self.assertRaises(HTTPError):
            self.request('PUT', '/api/routines/test/artwork', b'not-an-image')

    def test_app_data_export_import_keeps_assets_and_preferences(self):
        self.request("PUT", "/api/app-data/preferences", json.dumps({
            "library_favorites": ["mimic-502"], "unistore_favorites": ["871"],
        }).encode(), {"Content-Type": "application/json"})
        self.request("PUT", "/api/routines/test/audio", b"ID3backup")
        backup = self.request("GET", "/api/app-data/export").read()
        self.assertTrue(backup.startswith(b"PK"))
        (self.store.audio_dir / "test.mp3").unlink()
        response = json.load(self.request("PUT", "/api/app-data/import", backup, {
            "Content-Type": "application/zip",
        }))
        self.assertEqual(response["audio_output"], "browser")
        self.assertTrue((self.store.audio_dir / "test.mp3").exists())
        self.assertEqual(json.load(self.request("GET", "/api/app-data/preferences"))["unistore_favorites"], ["871"])

    def test_unistore_endpoint_is_read_only(self):
        from unittest.mock import patch
        with patch.object(self.player.robot, 'get_unistore_apps', return_value={
            'data': {'apps': [{'id': '754', 'name': 'Wannabe', 'install_status': 'installed'}]}
        }):
            result = json.loads(self.request('GET', '/api/unistore').read())
        self.assertEqual(result['apps'][0]['name'], 'Wannabe')
        self.assertFalse(result['apps'][0]['startable'])
        self.assertEqual(self.player.robot.log, [])

    def test_unistore_play_requires_confirmation_and_uses_instance(self):
        from unittest.mock import patch
        apps = {'data': {'apps': [{'id': '141', 'name': 'Fun Robot Twist',
            'instance_id': 'instance-141', 'install_status': 'installed'}]}}
        with patch.object(self.player.robot, 'get_unistore_apps', return_value=apps), \
             patch.object(self.player.robot, 'run_unistore_action', return_value={'status': 'accepted'}) as run:
            with self.assertRaises(HTTPError) as denied:
                self.request('POST', '/api/unistore/141/play', b'{}')
            self.assertEqual(denied.exception.code, 428)
            response = json.loads(self.request('POST', '/api/unistore/141/play', b'{}',
                {'X-G1-Safety-Confirmed': 'YES'}).read())
        self.assertEqual(response['app']['name'], 'Fun Robot Twist')
        run.assert_called_once_with('instance-141')

    def test_list_upload_and_play_confirmation(self):
        listing = json.load(urlopen(self.url + "/api/routines"))
        self.assertEqual(listing["routines"][0]["id"], "test")
        self.assertEqual(listing["routines"][1]["id"], "mimic-502")
        self.assertEqual(listing["routines"][1]["name"], "Popping1")
        self.assertEqual(listing["routines"][0]["category"], "dance")
        self.assertEqual(listing["routines"][1]["category"], "dance")
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
        stopped = json.load(self.request("POST", "/api/stop", b"{}"))
        self.assertEqual(stopped["state"], "stopped")
        self.assertEqual(self.player.robot.log[-1], {"type": "stop_custom_action", "fsm_id": None})
        reset = json.load(self.request("POST", "/api/reset", b"{}"))
        self.assertEqual(reset["state"], "idle")
        music = self.request("POST", "/api/routines/test/music", b"{}")
        self.assertEqual(music.status, 202)

    def test_cached_mimic_motion_can_play_in_dry_run(self):
        response = self.request(
            "POST", "/api/routines/mimic-502/play", b"{}",
            {"X-G1-Safety-Confirmed": "YES"},
        )
        self.assertEqual(response.status, 202)
        self.player._thread.join(timeout=1)
        self.assertEqual(self.player.robot.log[-1], {
            "type": "mimic_motion", "motion_id": 502, "fsm_id": 550502,
        })

    def test_mimic_motion_can_be_renamed_locally(self):
        renamed = json.load(self.request(
            "PUT", "/api/routines/mimic-502/title", b'{"title":"My Popping Dance"}',
            {"Content-Type": "application/json"},
        ))["routine"]
        self.assertEqual(renamed["song_title"], "My Popping Dance")
        listing = json.load(self.request("GET", "/api/routines"))["routines"]
        mimic = next(item for item in listing if item["id"] == "mimic-502")
        self.assertEqual(mimic["song_title"], "My Popping Dance")

    def test_action_can_be_hidden_without_deleting_robot_content(self):
        hidden = json.load(self.request("DELETE", "/api/library/routine/test/hide"))
        self.assertTrue(hidden["hidden"])
        listing = json.load(self.request("GET", "/api/routines"))["routines"]
        self.assertNotIn("test", [item["id"] for item in listing])
        self.assertTrue((self.store.routines_dir / "test.json").exists())

    def test_audio_output_setting(self):
        self.assertEqual(json.load(self.request("GET", "/api/settings"))["audio_output"], "browser")
        response = json.load(self.request(
            "PUT", "/api/settings/audio-output", b'{"audio_output":"usb"}',
            {"Content-Type": "application/json"},
        ))
        self.assertEqual(response["audio_output"], "usb")
        self.assertEqual(json.load(self.request("GET", "/api/settings"))["audio_output"], "usb")
        with self.assertRaises(HTTPError):
            self.request("PUT", "/api/settings/audio-output", b'{"audio_output":"headphones"}')

    def test_browser_audio_output_serves_attached_mp3(self):
        mp3 = b"ID3\x04\x00\x00browser-audio"
        self.request("PUT", "/api/routines/test/audio", mp3)
        self.assertEqual(self.request("GET", "/api/routines/test/audio-file").read(), mp3)
        response = json.load(self.request(
            "PUT", "/api/settings/audio-output", b'{"audio_output":"browser"}',
        ))
        self.assertEqual(response["audio_output"], "browser")

    def test_bluetooth_device_list_scan_and_single_connect(self):
        from unittest.mock import patch
        speaker = {"address": "AA:BB:CC:DD:EE:FF", "name": "Studio speaker",
                   "connected": True, "audio": True}
        with patch("g1_dancer.server.bluetooth.paired_devices", return_value=[speaker]), \
             patch("g1_dancer.server.bluetooth.scan", return_value=[speaker]) as scan, \
             patch("g1_dancer.server.bluetooth.connect", return_value=speaker) as connect:
            listed = json.load(self.request("GET", "/api/bluetooth/devices"))
            self.assertEqual(listed["devices"], [speaker])
            scanned = json.load(self.request("POST", "/api/bluetooth/scan", b"{}"))
            self.assertEqual(scanned["devices"], [speaker])
            connected = json.load(self.request(
                "POST", "/api/bluetooth/connect/AA%3ABB%3ACC%3ADD%3AEE%3AFF", b"{}",
            ))
        scan.assert_called_once_with(10)
        connect.assert_called_once_with("AA:BB:CC:DD:EE:FF")
        self.assertEqual(connected["device"], speaker)

    def test_preset_motion_list_and_safety_confirmation(self):
        motions = json.load(self.request("GET", "/api/motions"))["motions"]
        self.assertEqual(len(motions), 16)
        wave = next(item for item in motions if item["id"] == "high-wave")
        self.assertEqual(wave["name"], "Wave")
        self.assertIsNone(wave["audio"])
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

    def test_mp3_can_be_attached_and_played_without_the_preset(self):
        mp3 = b"ID3\x04\x00\x00attached-track"
        uploaded = json.load(self.request(
            "PUT", "/api/media/preset/high-wave/audio", mp3,
            {"X-Song-Title": "Wave song"},
        ))
        self.assertEqual(uploaded["action"]["audio"], "preset-high-wave.mp3")
        wave = next(item for item in json.load(self.request("GET", "/api/motions"))["motions"]
                    if item["id"] == "high-wave")
        self.assertEqual(wave["song_title"], "")
        self.assertEqual(wave["audio"], "preset-high-wave.mp3")
        music = self.request("POST", "/api/media/preset/high-wave/music", b"{}")
        self.assertEqual(music.status, 202)
        self.player._thread.join(timeout=1)
        self.assertEqual(self.player.robot.log, [])

    def test_hover_video_can_be_attached_to_any_action(self):
        video = b"\x00\x00\x00\x18ftypisom\x00\x00\x00\x00"
        uploaded = json.load(self.request(
            "PUT", "/api/media/preset/high-wave/video", video,
            {"Content-Type": "video/mp4"},
        ))
        self.assertEqual(uploaded["action"]["video"], "preset-high-wave.mp4")
        wave = next(item for item in json.load(self.request("GET", "/api/motions"))["motions"]
                    if item["id"] == "high-wave")
        self.assertIn("/api/media/preset/high-wave/video", wave["video_url"])
        response = self.request("GET", "/api/media/preset/high-wave/video")
        self.assertEqual(response.headers["Content-Type"], "video/mp4")
        self.assertEqual(response.read(), video)

    def test_walk_run_requires_confirmation_and_emergency_stop_is_immediate(self):
        with self.assertRaises(HTTPError) as caught:
            self.request("POST", "/api/robot/ready-mode", b"{}")
        self.assertEqual(caught.exception.code, 428)
        ready = json.load(self.request(
            "POST", "/api/robot/ready-mode", b"{}", {"X-G1-Safety-Confirmed": "YES"},
        ))
        self.assertEqual(ready["state"], "idle")
        self.assertEqual(self.player.robot.log[-1], {"type": "ready_mode", "fsm_id": 4})
        with self.assertRaises(HTTPError) as caught:
            self.request("POST", "/api/robot/walk-run", b"{}")
        self.assertEqual(caught.exception.code, 428)
        walk_run = json.load(self.request(
            "POST", "/api/robot/run-mode", b"{}", {"X-G1-Safety-Confirmed": "YES"},
        ))
        self.assertEqual(walk_run["state"], "idle")
        self.assertEqual(self.player.robot.log[-1], {"type": "run_mode", "internal_control": 2, "fsm_id": 500})
        stopped = json.load(self.request("POST", "/api/robot/damped-mode", b"{}"))
        self.assertEqual(stopped["state"], "stopped")
        self.assertEqual(self.player.robot.log[-1], {"type": "damped_mode", "fsm_id": 1})


if __name__ == "__main__":
    unittest.main()
