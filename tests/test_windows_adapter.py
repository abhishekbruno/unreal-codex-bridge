"""Unit tests for Windows-specific platform adapter."""

import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch, MagicMock

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from platform_adapter.windows import WindowsAdapter


class WindowsAdapterTests(unittest.TestCase):
    def setUp(self):
        self.adapter = WindowsAdapter()

    def test_windows_os_and_arch(self):
        os_info = self.adapter.detect_os()
        self.assertEqual(os_info["platform"], "windows")
        with patch("platform.machine", return_value="AMD64"):
            self.assertEqual(self.adapter.detect_architecture(), "x86_64")
        with patch("platform.machine", return_value="ARM64"):
            self.assertEqual(self.adapter.detect_architecture(), "arm64")

    def test_windows_resolve_editor_executable(self):
        root = Path("D:/UE_5.8")
        exe = self.adapter.resolve_editor_executable(root)
        self.assertEqual(exe, Path("D:/UE_5.8/Engine/Binaries/Win64/UnrealEditor.exe"))

    def test_windows_discover_engine_manifests(self):
        with tempfile.TemporaryDirectory() as temp:
            temp_path = Path(temp)
            manifest_dir = temp_path / "Epic/EpicGamesLauncher/Data/Manifests"
            manifest_dir.mkdir(parents=True)

            mock_engine = temp_path / "MockUE"
            (mock_engine / "Engine/Build").mkdir(parents=True)
            (mock_engine / "Engine/Build/Build.version").write_text("{}")

            manifest_file = manifest_dir / "UE58.item"
            manifest_data = {
                "AppName": "UE_5.8",
                "AppVersionString": "5.8.4",
                "InstallLocation": str(mock_engine)
            }
            manifest_file.write_text(json.dumps(manifest_data))

            with patch.dict("os.environ", {"PROGRAMDATA": str(temp_path)}):
                installs = self.adapter.discover_engine_installations()
                matched = [i for i in installs if i["path"] == mock_engine.resolve()]
                self.assertTrue(len(matched) >= 1)
                self.assertEqual(matched[0]["version"], "5.8.4")

    def test_windows_resolve_codex_binary(self):
        with patch("shutil.which") as mock_which:
            mock_which.side_effect = lambda name: "C:\\Program Files\\nodejs\\codex.cmd" if name == "codex.cmd" else None
            bin_path = self.adapter.resolve_codex_binary()
            self.assertEqual(bin_path, Path("C:/Program Files/nodejs/codex.cmd").resolve())

    def test_windows_inspect_port_owner(self):
        mock_netstat = (
            "  Proto  Local Address          Foreign Address        State           PID\n"
            "  TCP    127.0.0.1:8000         0.0.0.0:0              LISTENING       23088\n"
            "  TCP    0.0.0.0:135            0.0.0.0:0              LISTENING       1120\n"
        )
        with patch("subprocess.check_output", return_value=mock_netstat):
            pid = self.adapter.inspect_port_owner(8000)
            self.assertEqual(pid, 23088)
            self.assertIsNone(self.adapter.inspect_port_owner(9999))

    def test_windows_verify_project_identity(self):
        with patch.object(self.adapter, "inspect_port_owner", return_value=23088):
            mock_cim = json.dumps({
                "ProcessId": 23088,
                "ExecutablePath": "D:\\UE_5.8\\Engine\\Binaries\\Win64\\UnrealEditor.exe",
                "CommandLine": 'UnrealEditor.exe "D:\\Projects\\My Game\\My Game.uproject" -ModelContextProtocolStartServer'
            })
            mock_run = MagicMock(returncode=0, stdout=mock_cim)
            with patch("subprocess.run", return_value=mock_run):
                proj = Path("D:/Projects/My Game/My Game.uproject")
                self.assertTrue(self.adapter.verify_project_identity(8000, proj, Path("D:/UE_5.8")))
                self.assertFalse(self.adapter.verify_project_identity(8000, Path("D:/Other/Other.uproject"), Path("D:/UE_5.8")))

    def test_windows_launch_editor_args(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp).resolve()
            proj = root / "My Game" / "My Game.uproject"
            proj.parent.mkdir(parents=True)
            proj.write_text('{"FileVersion": 3}')

            engine = root / "UE_5.8"
            exe = engine / "Engine/Binaries/Win64/UnrealEditor.exe"
            exe.parent.mkdir(parents=True)
            exe.touch()

            with patch.object(self.adapter, "is_port_in_use", return_value=False), \
                 patch("subprocess.Popen") as mock_popen:
                mock_proc = MagicMock(pid=12345)
                mock_popen.return_value = mock_proc

                res = self.adapter.launch_editor(proj, engine, port=8100)
                self.assertEqual(res["status"], "launched")
                self.assertEqual(res["pid"], 12345)

                cmd = mock_popen.call_args[0][0]
                self.assertEqual(cmd[0], str(exe))
                self.assertEqual(cmd[1], str(proj))
                self.assertIn("-ModelContextProtocolStartServer", cmd)
                self.assertIn("-ModelContextProtocolPort=8100", cmd)


if __name__ == "__main__":
    unittest.main()
