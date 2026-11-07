import importlib
import importlib.util
import json
import sys
import tempfile
import unittest
from pathlib import Path


DESKTOP_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(DESKTOP_ROOT))


class DesktopSettingsTests(unittest.TestCase):
    def settings_module(self):
        try:
            spec = importlib.util.find_spec("ict_desktop.settings")
        except ModuleNotFoundError:
            spec = None
        self.assertIsNotNone(spec, "Desktop service settings must be implemented")
        return importlib.import_module("ict_desktop.settings")

    def test_saves_and_loads_only_the_service_url(self):
        settings = self.settings_module()
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "settings.json"

            settings.save_api_base_url("https://api.example.com", path=path)

            self.assertEqual(settings.load_api_base_url(path=path), "https://api.example.com")
            self.assertEqual(json.loads(path.read_text(encoding="utf-8")), {"api_base_url": "https://api.example.com"})

    def test_command_line_and_environment_override_saved_address(self):
        settings = self.settings_module()
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "settings.json"
            settings.save_api_base_url("https://saved.example.com", path=path)

            self.assertEqual(
                settings.resolve_api_base_url(cli_value="https://cli.example.com", env_value="https://env.example.com", path=path),
                "https://cli.example.com",
            )
            self.assertEqual(
                settings.resolve_api_base_url(env_value="https://env.example.com", path=path),
                "https://env.example.com",
            )
            self.assertEqual(settings.resolve_api_base_url(path=path), "https://saved.example.com")

    def test_ignores_corrupt_saved_settings_and_uses_default(self):
        settings = self.settings_module()
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "settings.json"
            path.write_text("{broken", encoding="utf-8")

            self.assertEqual(settings.resolve_api_base_url(path=path), settings.DEFAULT_API_BASE_URL)

    def test_rejects_remote_http_before_saving(self):
        settings = self.settings_module()
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "settings.json"

            with self.assertRaises(settings.DesktopApiError):
                settings.save_api_base_url("http://api.example.com", path=path)

            self.assertFalse(path.exists())


if __name__ == "__main__":
    unittest.main()
