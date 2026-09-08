import tempfile
import unittest
from pathlib import Path

from g1_dancer.config import initialize_config, load_config


class ConfigTests(unittest.TestCase):
    def test_yaml_round_trip(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "config.yaml"
            created = initialize_config(
                path, data_dir=f"{directory}/data", interface="eth0", host="0.0.0.0", port=8787
            )
            loaded = load_config(path)
            self.assertEqual(loaded, created)
            self.assertIn("network_interface: \"eth0\"", path.read_text())

    def test_legacy_token_is_ignored(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "config.yaml"
            path.write_text('data_dir: "/tmp/g1"\napi_token: "old-secret"\n')
            self.assertEqual(load_config(path).data_dir, "/tmp/g1")


if __name__ == "__main__":
    unittest.main()
