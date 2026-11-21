"""Unit tests for platform detection and adapter factory."""

import platform
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from platform_adapter import (
    PlatformAdapter,
    WindowsAdapter,
    MacOSAdapter,
    detect_system,
    get_platform_adapter,
    PlatformNotSupportedError
)


class PlatformDetectTests(unittest.TestCase):
    def test_detect_system_windows(self):
        with patch.object(platform, "system", return_value="Windows"):
            self.assertEqual(detect_system(), "windows")

    def test_detect_system_darwin(self):
        with patch.object(platform, "system", return_value="Darwin"):
            self.assertEqual(detect_system(), "macos")

    def test_detect_system_unsupported(self):
        with patch.object(platform, "system", return_value="FreeBSD"):
            with self.assertRaises(PlatformNotSupportedError):
                detect_system()

    def test_factory_returns_correct_adapter(self):
        win = get_platform_adapter(force_platform="windows")
        self.assertIsInstance(win, WindowsAdapter)
        self.assertEqual(win.name, "windows")

        mac = get_platform_adapter(force_platform="macos")
        self.assertIsInstance(mac, MacOSAdapter)
        self.assertEqual(mac.name, "macos")

    def test_factory_rejects_invalid_platform(self):
        with self.assertRaises(PlatformNotSupportedError):
            get_platform_adapter(force_platform="solaris")

    def test_current_platform_adapter_loads(self):
        adapter = get_platform_adapter()
        self.assertIsInstance(adapter, PlatformAdapter)
        os_info = adapter.detect_os()
        self.assertIn("system", os_info)
        self.assertIn("machine", os_info)


if __name__ == "__main__":
    unittest.main()
