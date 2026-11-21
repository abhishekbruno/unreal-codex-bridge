"""Unit tests for the unified cross-platform editor lifecycle CLI."""

import argparse
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch, MagicMock

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import editor_lifecycle
from platform_adapter.base import PlatformAdapter


class MockAdapter(PlatformAdapter):
    @property
    def name(self): return "mock"
    def detect_os(self): return {"platform": "mock_os", "system": "Mock", "release": "1.0", "machine": "x86_64"}
    def detect_architecture(self): return "x86_64"
    def discover_engine_installations(self): return [{"version": "5.8.4", "path": Path("/mock/UE"), "source": "test"}]
    def resolve_engine_root(self, explicit=None, project=None): return Path("/mock/UE")
    def resolve_editor_executable(self, root): return Path("/mock/UE/Editor")
    def resolve_codex_binary(self): return Path("/mock/bin/codex")
    def inspect_port_owner(self, port): return 1234
    def find_running_editor_processes(self): return []
    def verify_project_identity(self, port, project, engine=None): return True
    def check_toolchain_prerequisites(self): return {"has_compiler": True}


class EditorLifecycleTests(unittest.TestCase):
    def setUp(self):
        self.adapter = MockAdapter()

    def test_lifecycle_detect(self):
        args = argparse.Namespace(search_dir=None)
        res = editor_lifecycle.cmd_detect(args, self.adapter)
        self.assertEqual(res["architecture"], "x86_64")
        self.assertEqual(len(res["installed_engines"]), 1)
        self.assertEqual(res["installed_engines"][0]["version"], "5.8.4")

    def test_lifecycle_prepare_updates_and_backs_up(self):
        with tempfile.TemporaryDirectory() as temp:
            temp_path = Path(temp)
            proj = temp_path / "TestGame.uproject"
            proj.write_text('{"FileVersion": 3, "Plugins": []}')

            config_dir = temp_path / "Config"
            config_dir.mkdir(parents=True)
            engine_ini = config_dir / "DefaultEngine.ini"
            engine_ini.write_text("[Core.System]\nPaths=None\n")

            args = argparse.Namespace(project=str(proj), engine=None, port=8000)
            res = editor_lifecycle.cmd_prepare(args, self.adapter)

            self.assertEqual(res["status"], "prepared")
            self.assertTrue(res["uproject_modified"])
            self.assertTrue(Path(res["uproject_backup"]).is_file())

            # Check .uproject content
            data = json.loads(proj.read_text())
            plugin_names = [p["Name"] for p in data["Plugins"]]
            self.assertIn("ModelContextProtocol", plugin_names)
            self.assertIn("AllToolsets", plugin_names)

            # Check DefaultEngine.ini loopback binding
            ini_content = engine_ini.read_text()
            self.assertIn("[HTTPServer.Listeners]", ini_content)
            self.assertIn("DefaultBindAddress=127.0.0.1", ini_content)

    def test_lifecycle_launch(self):
        with tempfile.TemporaryDirectory() as temp:
            proj = Path(temp) / "TestGame.uproject"
            proj.write_text('{"FileVersion": 3}')

            with patch.object(self.adapter, "launch_editor", return_value={"status": "launched", "pid": 4321}):
                args = argparse.Namespace(project=str(proj), engine=None, port=8000)
                res = editor_lifecycle.cmd_launch(args, self.adapter)
                self.assertEqual(res["status"], "launched")
                self.assertEqual(res["pid"], 4321)

    def test_lifecycle_status_reporting(self):
        with tempfile.TemporaryDirectory() as temp:
            proj = Path(temp) / "TestGame.uproject"
            proj.write_text('{"FileVersion": 3}')

            with patch.object(self.adapter, "is_port_in_use", return_value=False), \
                 patch.object(self.adapter, "resolve_editor_executable", return_value=Path(temp)/"exe"):
                args = argparse.Namespace(project=str(proj), engine=None, port=8000, timeout=5)
                res = editor_lifecycle.cmd_status(args, self.adapter)
                self.assertEqual(res["mcp_status"], "offline")
                self.assertFalse(res["is_listening"])

    def test_lifecycle_uninstall(self):
        with tempfile.TemporaryDirectory() as temp:
            proj = Path(temp) / "TestGame.uproject"
            proj.write_text('{"FileVersion": 3}')

            codex_dir = Path(temp) / ".codex"
            codex_dir.mkdir(parents=True)
            codex_toml = codex_dir / "config.toml"
            codex_toml.write_text('[mcp_servers.unreal-mcp]\nurl = "http://127.0.0.1:8000/mcp"\n')

            args = argparse.Namespace(project=str(proj))
            res = editor_lifecycle.cmd_uninstall(args, self.adapter)
            self.assertEqual(res["status"], "uninstalled")
            self.assertTrue(res["codex_config_reverted"])
            self.assertNotIn("[mcp_servers.unreal-mcp]", codex_toml.read_text())


if __name__ == "__main__":
    unittest.main()
