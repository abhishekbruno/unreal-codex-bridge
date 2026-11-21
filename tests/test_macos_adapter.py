"""Unit tests for macOS-specific platform adapter (Apple Silicon arm64 & Intel x86_64)."""

from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch, MagicMock

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from platform_adapter.macos import MacOSAdapter


class MacOSAdapterTests(unittest.TestCase):
    def setUp(self):
        self.adapter = MacOSAdapter()

    def test_macos_os_and_arch(self):
        with patch("platform.system", return_value="Darwin"), \
             patch("platform.release", return_value="24.1.0"), \
             patch("platform.mac_ver", return_value=("15.1.0", ("", "", ""), "")):
            with patch("platform.machine", return_value="arm64"):
                os_info = self.adapter.detect_os()
                self.assertEqual(os_info["platform"], "macos")
                self.assertTrue(os_info["is_apple_silicon"])
                self.assertEqual(self.adapter.detect_architecture(), "arm64")

            with patch("platform.machine", return_value="x86_64"):
                os_info = self.adapter.detect_os()
                self.assertFalse(os_info["is_apple_silicon"])
                self.assertEqual(self.adapter.detect_architecture(), "x86_64")

    def test_macos_resolve_editor_executable(self):
        root = Path("/Users/Shared/Epic Games/UE_5.8")
        exe = self.adapter.resolve_editor_executable(root)
        expected = root / "Engine/Binaries/Mac/UnrealEditor.app/Contents/MacOS/UnrealEditor"
        self.assertEqual(exe, expected)

    def test_macos_discover_engine_installations(self):
        with tempfile.TemporaryDirectory() as temp:
            temp_path = Path(temp)
            mock_epic = temp_path / "Epic Games"
            mock_ue58 = mock_epic / "UE_5.8"
            exe = mock_ue58 / MacOSAdapter.MAC_BINARY_REL
            exe.parent.mkdir(parents=True)
            exe.touch()

            self.adapter.STANDARD_EPIC_ROOT = mock_epic
            installs = self.adapter.discover_engine_installations()
            self.assertEqual(len(installs), 1)
            self.assertEqual(installs[0]["version"], "UE_5.8")
            self.assertEqual(installs[0]["path"], mock_ue58)

    def test_macos_resolve_codex_binary_rejects_cmd(self):
        with patch("shutil.which") as mock_which:
            # If which returns a .cmd file, macOS adapter must ignore it
            mock_which.return_value = "/usr/local/bin/codex.cmd"
            with self.assertRaises(FileNotFoundError):
                self.adapter.resolve_codex_binary()

            # When valid unix binary returned
            mock_which.return_value = "/opt/homebrew/bin/codex"
            bin_path = self.adapter.resolve_codex_binary()
            self.assertEqual(bin_path, Path("/opt/homebrew/bin/codex"))

    def test_macos_inspect_port_owner(self):
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=0, stdout="p98765\n")
            pid = self.adapter.inspect_port_owner(8000)
            self.assertEqual(pid, 98765)

            mock_run.return_value = MagicMock(returncode=1, stdout="")
            self.assertIsNone(self.adapter.inspect_port_owner(8000))

    def test_macos_verify_project_identity(self):
        with patch.object(self.adapter, "inspect_port_owner", return_value=98765):
            mock_cmd = (
                "/Users/Shared/Epic Games/UE_5.8/Engine/Binaries/Mac/UnrealEditor.app/Contents/MacOS/UnrealEditor "
                "/Users/developer/Games/MyGame/MyGame.uproject -ModelContextProtocolStartServer"
            )
            mock_run = MagicMock(returncode=0, stdout=mock_cmd)
            with patch("subprocess.run", return_value=mock_run):
                proj = Path("/Users/developer/Games/MyGame/MyGame.uproject")
                engine = Path("/Users/Shared/Epic Games/UE_5.8")
                self.assertTrue(self.adapter.verify_project_identity(8000, proj, engine))
                self.assertFalse(self.adapter.verify_project_identity(8000, Path("/Other/Other.uproject"), engine))

    def test_regression_stale_log_fallback_rejected(self):
        with tempfile.TemporaryDirectory() as temp:
            temp_path = Path(temp)
            proj = temp_path / "MyGame/MyGame.uproject"
            proj.parent.mkdir(parents=True)
            proj.write_text('{"FileVersion": 3}')

            # Create a recent log file in Saved/Logs
            logs_dir = proj.parent / "Saved/Logs"
            logs_dir.mkdir(parents=True)
            log_file = logs_dir / "MyGame.log"
            log_file.write_text("recent log")

            # Fake process that is NOT UnrealEditor
            with patch.object(self.adapter, "inspect_port_owner", return_value=1234):
                mock_run = MagicMock(returncode=0, stdout="python other_server.py --port 8000")
                with patch("subprocess.run", return_value=mock_run):
                    res = self.adapter.verify_project_identity(8000, proj, Path("/Users/Shared/Epic Games/UE_5.8"))
                    self.assertFalse(res, "Stale or unverified log fallback must be rejected")

    def test_regression_unverified_process_name_rejected(self):
        with tempfile.TemporaryDirectory() as temp:
            temp_path = Path(temp)
            proj = temp_path / "MyGame/MyGame.uproject"
            proj.parent.mkdir(parents=True)
            proj.write_text('{"FileVersion": 3}')

            # Create a recent log file
            logs_dir = proj.parent / "Saved/Logs"
            logs_dir.mkdir(parents=True)
            (logs_dir / "MyGame.log").write_text("recent log")

            with patch.object(self.adapter, "inspect_port_owner", return_value=1234):
                # Process with 'unrealeditor' in name but is a python script
                mock_run = MagicMock(returncode=0, stdout="python unrealeditor_fake.py --port 8000")
                with patch("subprocess.run", return_value=mock_run):
                    res = self.adapter.verify_project_identity(8000, proj, Path("/Users/Shared/Epic Games/UE_5.8"))
                    self.assertFalse(res, "Process with unverified executable must not be accepted")

    def test_regression_wrong_engine_rejected(self):
        with patch.object(self.adapter, "inspect_port_owner", return_value=98765):
            mock_cmd = (
                "/Other/Engine/Binaries/Mac/UnrealEditor.app/Contents/MacOS/UnrealEditor "
                "/Users/developer/Games/MyGame/MyGame.uproject -ModelContextProtocolStartServer"
            )
            mock_run = MagicMock(returncode=0, stdout=mock_cmd)
            with patch("subprocess.run", return_value=mock_run):
                proj = Path("/Users/developer/Games/MyGame/MyGame.uproject")
                engine = Path("/Users/Shared/Epic Games/UE_5.8")
                self.assertFalse(self.adapter.verify_project_identity(8000, proj, engine))

    def test_regression_os_level_executable_verification(self):
        with patch.object(self.adapter, "inspect_port_owner", return_value=98765):
            # Command line says UnrealEditor, but OS API reveals it's python
            mock_cmd = (
                "/Users/Shared/Epic Games/UE_5.8/Engine/Binaries/Mac/UnrealEditor.app/Contents/MacOS/UnrealEditor "
                "/Users/developer/Games/MyGame/MyGame.uproject"
            )
            mock_run = MagicMock(returncode=0, stdout=mock_cmd)
            with patch.object(self.adapter, "get_process_executable", return_value=Path("/usr/local/bin/python3")):
                with patch("subprocess.run", return_value=mock_run):
                    proj = Path("/Users/developer/Games/MyGame/MyGame.uproject")
                    engine = Path("/Users/Shared/Epic Games/UE_5.8")
                    self.assertFalse(self.adapter.verify_project_identity(8000, proj, engine),
                                     "OS-level executable mismatch must reject process")

    def test_regression_lookalike_engine_prefix_rejected(self):
        with patch.object(self.adapter, "inspect_port_owner", return_value=98765):
            # Lookalike directory UE_5.8_fake has UE_5.8 as prefix string
            fake_exe = Path("/Users/Shared/Epic Games/UE_5.8_fake/Engine/Binaries/Mac/UnrealEditor.app/Contents/MacOS/UnrealEditor")
            mock_cmd = f"{fake_exe} /Users/developer/Games/MyGame/MyGame.uproject -ModelContextProtocolStartServer"
            mock_run = MagicMock(returncode=0, stdout=mock_cmd)
            with patch.object(self.adapter, "get_process_executable", return_value=fake_exe):
                with patch("subprocess.run", return_value=mock_run):
                    proj = Path("/Users/developer/Games/MyGame/MyGame.uproject")
                    engine = Path("/Users/Shared/Epic Games/UE_5.8")
                    self.assertFalse(self.adapter.verify_project_identity(8000, proj, engine),
                                     "Lookalike engine prefix must be rejected")

    def test_regression_ambiguous_relative_project_path_rejected(self):
        with patch.object(self.adapter, "inspect_port_owner", return_value=98765):
            # Ambiguous relative path passed in command line without absolute resolution
            mock_cmd = (
                "/Users/Shared/Epic Games/UE_5.8/Engine/Binaries/Mac/UnrealEditor.app/Contents/MacOS/UnrealEditor "
                "MyGame.uproject -ModelContextProtocolStartServer"
            )
            mock_run = MagicMock(returncode=0, stdout=mock_cmd)
            with patch("subprocess.run", return_value=mock_run):
                proj = Path("/Users/developer/Games/MyGame/MyGame.uproject")
                engine = Path("/Users/Shared/Epic Games/UE_5.8")
                self.assertFalse(self.adapter.verify_project_identity(8000, proj, engine),
                                 "Ambiguous relative project path must be rejected")

    def test_regression_multiple_uproject_args_rejected(self):
        with patch.object(self.adapter, "inspect_port_owner", return_value=98765):
            # Multiple conflicting uproject paths passed
            mock_cmd = (
                "/Users/Shared/Epic Games/UE_5.8/Engine/Binaries/Mac/UnrealEditor.app/Contents/MacOS/UnrealEditor "
                "/Users/developer/Games/MyGame/MyGame.uproject /Users/developer/Other/Other.uproject"
            )
            mock_run = MagicMock(returncode=0, stdout=mock_cmd)
            with patch("subprocess.run", return_value=mock_run):
                proj = Path("/Users/developer/Games/MyGame/MyGame.uproject")
                engine = Path("/Users/Shared/Epic Games/UE_5.8")
                self.assertFalse(self.adapter.verify_project_identity(8000, proj, engine),
                                 "Conflicting uproject arguments must be rejected")

    def test_macos_launch_editor_args(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp).resolve()
            proj = root / "My Game" / "My Game.uproject"
            proj.parent.mkdir(parents=True)
            proj.write_text('{"FileVersion": 3}')

            engine = root / "UE_5.8"
            exe = engine / MacOSAdapter.MAC_BINARY_REL
            exe.parent.mkdir(parents=True)
            exe.touch()

            with patch.object(self.adapter, "is_port_in_use", return_value=False), \
                 patch("subprocess.Popen") as mock_popen:
                mock_proc = MagicMock(pid=54321)
                mock_popen.return_value = mock_proc

                res = self.adapter.launch_editor(proj, engine, port=8200)
                self.assertEqual(res["status"], "launched")
                self.assertEqual(res["pid"], 54321)

                cmd = mock_popen.call_args[0][0]
                self.assertEqual(cmd[0], str(exe))
                self.assertEqual(cmd[1], str(proj))
                self.assertIn("-ModelContextProtocolStartServer", cmd)
                self.assertIn("-ModelContextProtocolPort=8200", cmd)


if __name__ == "__main__":
    unittest.main()
