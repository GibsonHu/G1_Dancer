import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock

from g1_dancer.unistore import UniStoreCatalog


class UniStoreTests(unittest.TestCase):
    def test_discovery_refresh_and_offline_cache(self):
        with tempfile.TemporaryDirectory() as root:
            catalog = UniStoreCatalog(Path(root))
            robot = Mock()
            robot.get_unistore_apps.return_value = {"data": {"apps": [
                {"id": "754", "name": "Wannabe", "install_status": "installed",
                 "version": "1.0.1", "token": "do-not-persist", "cover": "javascript:bad"},
                {"id": "759", "name": "Not installed", "install_status": "removed"},
            ]}}
            result = catalog.discover(robot)
            self.assertFalse(result["cached"])
            self.assertEqual([a["name"] for a in result["apps"]], ["Wannabe"])
            self.assertFalse(result["apps"][0]["startable"])
            self.assertNotIn("cover", result["apps"][0])
            self.assertNotIn("do-not-persist", catalog.path.read_text())
            robot.get_unistore_apps.side_effect = RuntimeError("offline")
            cached = UniStoreCatalog(Path(root)).discover(robot)
            self.assertTrue(cached["cached"])
            self.assertEqual(cached["apps"], result["apps"])
            self.assertIsNotNone(cached["error"])
            robot.get_unistore_apps.side_effect = None
            robot.get_unistore_apps.return_value = {"data": {"apps": []}}
            self.assertEqual(catalog.discover(robot)["apps"], [])

    def test_chinese_titles_are_translated_before_the_ui_receives_them(self):
        with tempfile.TemporaryDirectory() as root:
            catalog = UniStoreCatalog(Path(root))
            app = catalog.decode([{
                "id": "325", "name": "小城夏天元气舞", "install_status": "installed"
            }])[0]
            self.assertEqual(app["name"], "Small Town Summer Dance")
            self.assertEqual(app["original_name"], "小城夏天元气舞")

    def test_invalid_response_does_not_replace_cache(self):
        with tempfile.TemporaryDirectory() as root:
            catalog = UniStoreCatalog(Path(root))
            robot = Mock()
            robot.get_unistore_apps.return_value = {"data": {"apps": None}}
            self.assertIsNotNone(catalog.discover(robot)["error"])
