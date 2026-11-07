import importlib.util
import subprocess
import sys
import unittest
from pathlib import Path


DESKTOP_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(DESKTOP_ROOT))


class DesktopEntrypointTests(unittest.TestCase):
    def test_help_lists_the_api_endpoint_setting_without_starting_a_window(self):
        self.assertIsNotNone(importlib.util.find_spec("ict_desktop.__main__"), "The desktop entrypoint must be implemented")

        result = subprocess.run(
            [sys.executable, "-m", "ict_desktop", "--help"],
            cwd=DESKTOP_ROOT,
            capture_output=True,
            text=True,
            check=False,
            timeout=5,
        )

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("--api-base-url", result.stdout)
        self.assertIn("usage:", result.stdout.lower())


if __name__ == "__main__":
    unittest.main()
