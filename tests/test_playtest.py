"""Unit tests for the Play-In-Editor (PIE) playtest telemetry and session runner."""

from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch, MagicMock

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import playtest


class PlaytestTests(unittest.TestCase):
    def test_find_project_log(self):
        with tempfile.TemporaryDirectory() as temp:
            temp_path = Path(temp)
            proj = temp_path / "SpaceShooter.uproject"
            proj.write_text('{"FileVersion": 3}')

            logs_dir = temp_path / "Saved/Logs"
            logs_dir.mkdir(parents=True)
            log_file = logs_dir / "SpaceShooter.log"
            log_file.write_text("LogInit: Display: Unreal Engine 5.8.4 initialized.\n")

            found = playtest.find_project_log(proj)
            self.assertEqual(found, log_file)

    def test_inspect_log_telemetry(self):
        with tempfile.TemporaryDirectory() as temp:
            log_file = Path(temp) / "Game.log"
            content = (
                "LogInit: Display: Starting game.\n"
                "LogBlueprintUserMessages: Star collected: 1/5\n"
                "LogBlueprintUserMessages: Warning: Character speed exceeds max.\n"
                "LogBlueprintUserMessages: Star collected: 5/5\n"
                "LogBlueprintUserMessages: Gate unlocked.\n"
                "LogScript: Error: Blueprint Runtime Error: Attempted to access None\n"
            )
            log_file.write_text(content, encoding="utf-8")

            res = playtest.inspect_log_telemetry(log_file)
            self.assertEqual(res["total_lines"], 6)
            self.assertEqual(len(res["errors"]), 1)
            self.assertIn("Blueprint Runtime Error", res["errors"][0])
            self.assertEqual(len(res["warnings"]), 1)
            self.assertEqual(len(res["gameplay_events"]), 3)

    def test_run_playtest_flow(self):
        with tempfile.TemporaryDirectory() as temp:
            proj = Path(temp) / "Game.uproject"
            proj.write_text('{"FileVersion": 3}')

            logs_dir = Path(temp) / "Saved/Logs"
            logs_dir.mkdir(parents=True)
            log_file = logs_dir / "Game.log"
            log_file.touch()

            def mock_sleep(seconds):
                log_file.write_text("LogInit: Engine started.\nLogTemp: Star 1 collected.\n")

            with patch("playtest.Client") as mock_client_cls, \
                 patch("playtest.time.sleep", side_effect=mock_sleep):
                mock_client = MagicMock()
                mock_client.tools.return_value = [{"name": "call_tool"}]
                mock_client.call.return_value = {"content": []}
                mock_client_cls.return_value = mock_client

                res = playtest.run_playtest(proj, duration=1)
                self.assertEqual(res["status"], "completed")
                self.assertTrue(res["evaluation"]["clean_run"])
                self.assertEqual(res["evaluation"]["gameplay_signals_found"], 1)


if __name__ == "__main__":
    unittest.main()
