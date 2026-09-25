import unittest
from unittest.mock import patch

from g1_dancer import bluetooth


class BluetoothTests(unittest.TestCase):
    def test_terminal_cleaning_keeps_device_rows_separate(self):
        text = "\x1b[0;94mDevice 4C:3C:8F:30:26:8D JBL Go 4\x1b[0m\nDevice F4:4E:FC:01:33:2A AIRHUG 01"
        with patch.object(bluetooth, "_run", return_value=text):
            devices = bluetooth._devices("devices")
        self.assertEqual([item["name"] for item in devices], ["JBL Go 4", "AIRHUG 01"])

    def test_scan_only_returns_audio_devices(self):
        devices = [
            {"address": "4C:3C:8F:30:26:8D", "name": "JBL Go 4"},
            {"address": "41:16:56:A5:73:13", "name": "Nearby tracker"},
        ]
        with patch.object(bluetooth, "_run", return_value=""), \
             patch.object(bluetooth, "_devices", return_value=devices), \
             patch.object(bluetooth, "_is_audio", side_effect=[True, False]):
            self.assertEqual(bluetooth.scan(1), [devices[0]])


if __name__ == "__main__":
    unittest.main()
