"""Unit and regression tests for playtest runner and runtime telemetry."""

import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import MagicMock, patch

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

import playtest
from playtest import PIEState


class PlaytestTests(unittest.TestCase):
    def setUp(self):
        self.maxDiff = None

    def test_find_project_log(self):
        with tempfile.TemporaryDirectory() as temp:
            proj = Path(temp) / "MyGame/MyGame.uproject"
            proj.parent.mkdir(parents=True)
            proj.touch()

            logs_dir = proj.parent / "Saved/Logs"
            logs_dir.mkdir(parents=True)
            expected_log = logs_dir / "MyGame.log"
            expected_log.touch()

            found = playtest.find_project_log(proj)
            self.assertEqual(found, expected_log)

    def test_inspect_log_telemetry(self):
        with tempfile.TemporaryDirectory() as temp:
            log_file = Path(temp) / "Test.log"
            log_content = (
                "LogInit: Display: Starting game.\n"
                "LogScript: Warning: Property value uninitialized.\n"
                "LogBlueprint: Error: Accessed None in BP_Player.\n"
                "LogGame: Display: Player collected star 1 of 5.\n"
                "LogGame: Display: Score: 100\n"
            )
            log_file.write_text(log_content, encoding="utf-8")

            res = playtest.inspect_log_telemetry(log_file)
            self.assertEqual(res["total_lines"], 5)
            self.assertEqual(len(res["errors"]), 1)
            self.assertIn("Accessed None", res["errors"][0])
            self.assertEqual(len(res["warnings"]), 1)
            self.assertEqual(len(res["gameplay_events"]), 2)

    def test_run_playtest_flow(self):
        with tempfile.TemporaryDirectory() as temp:
            proj = Path(temp) / "Game.uproject"
            proj.write_text('{"FileVersion": 3}')

            logs_dir = Path(temp) / "Saved/Logs"
            logs_dir.mkdir(parents=True)
            log_file = logs_dir / "Game.log"
            log_file.write_text("LogInit: Engine started.\n")

            def mock_sleep(_duration):
                with log_file.open("a", encoding="utf-8") as f:
                    f.write("LogGame: Player picked up star 1!\n")

            with patch("playtest.Client") as mock_client_cls, \
                 patch("playtest.time.sleep", side_effect=mock_sleep):
                mock_client = MagicMock()
                mock_client.tools.return_value = [{"name": "call_tool"}]
                mock_client.call.return_value = {"content": []}
                mock_client_cls.return_value = mock_client

                res = playtest.run_playtest(proj, duration=1)
                self.assertEqual(res["status"], "completed")
                self.assertEqual(res["pie_state"], PIEState.STOPPED)
                self.assertTrue(res["verification"]["successful_pie_startup"])
                self.assertTrue(res["verification"]["stop_successful"])
                self.assertTrue(res["evaluation"]["clean_run"])
                self.assertTrue(res["evaluation"]["gameplay_verified"])
                self.assertEqual(res["evaluation"]["gameplay_signals_found"], 1)

    def test_regression_tool_error_fails_pie_and_clean_run(self):
        with tempfile.TemporaryDirectory() as temp:
            proj = Path(temp) / "Game.uproject"
            proj.write_text('{"FileVersion": 3}')

            logs_dir = Path(temp) / "Saved/Logs"
            logs_dir.mkdir(parents=True)
            log_file = logs_dir / "Game.log"
            log_file.write_text("LogInit: Engine started.\n")

            with patch("playtest.Client") as mock_client_cls, \
                 patch("playtest.time.sleep", return_value=None):
                mock_client = MagicMock()
                mock_client.tools.return_value = [{"name": "call_tool"}]
                # Simulate tool error
                mock_client.call.return_value = {"content": [{"type": "text", "text": "Failed to enter PIE"}], "isError": True}
                mock_client_cls.return_value = mock_client

                res = playtest.run_playtest(proj, duration=1)
                self.assertEqual(res["status"], "failed")
                self.assertEqual(res["pie_state"], PIEState.FAILED)
                self.assertFalse(res["verification"]["successful_pie_startup"])
                self.assertFalse(res["evaluation"]["clean_run"])

    def test_regression_missing_log_never_reports_clean_run(self):
        with tempfile.TemporaryDirectory() as temp:
            proj = Path(temp) / "GameWithoutLogs.uproject"
            proj.write_text('{"FileVersion": 3}')
            # Notice: NO log file created!

            with patch("playtest.Client") as mock_client_cls, \
                 patch("playtest.time.sleep", return_value=None):
                mock_client = MagicMock()
                mock_client.tools.return_value = [{"name": "call_tool"}]
                mock_client.call.return_value = {"content": [], "isError": False}
                mock_client_cls.return_value = mock_client

                res = playtest.run_playtest(proj, duration=1)
                # When runtime evidence is missing, clean_run MUST NEVER be True
                self.assertFalse(res["evaluation"]["clean_run"])
                self.assertFalse(res["verification"]["runtime_log_available"])
                self.assertIn("UNAVAILABLE", res["evaluation"].get("evidence_status", ""))

    def test_regression_unsuccessful_pie_distinguished_from_success(self):
        with tempfile.TemporaryDirectory() as temp:
            proj = Path(temp) / "Game.uproject"
            proj.write_text('{"FileVersion": 3}')

            with patch("playtest.Client") as mock_client_cls, \
                 patch("playtest.time.sleep", return_value=None):
                mock_client = MagicMock()
                mock_client.tools.return_value = [{"name": "other_tool"}] # call_tool not available
                mock_client_cls.return_value = mock_client

                res = playtest.run_playtest(proj, duration=1)
                self.assertEqual(res["status"], "failed")
                self.assertEqual(res["pie_state"], PIEState.FAILED)
                self.assertFalse(res["verification"]["successful_pie_startup"])
                self.assertFalse(res["evaluation"]["clean_run"])

    def test_clean_run_never_implies_gameplay_success(self):
        """Zero errors in log must never equate to gameplay verified when signals are absent."""
        with tempfile.TemporaryDirectory() as temp:
            proj = Path(temp) / "CleanGame.uproject"
            proj.write_text('{"FileVersion": 3}')

            logs_dir = Path(temp) / "Saved/Logs"
            logs_dir.mkdir(parents=True)
            log_file = logs_dir / "CleanGame.log"
            # Log has engine lines but zero gameplay events
            log_file.write_text("LogInit: Engine started.\nLogInit: Display: Game ready.\n")

            def mock_sleep(_duration):
                with log_file.open("a", encoding="utf-8") as f:
                    f.write("LogEngine: Tick 1 - Game loop active.\n")

            with patch("playtest.Client") as mock_client_cls, \
                 patch("playtest.time.sleep", side_effect=mock_sleep):
                mock_client = MagicMock()
                mock_client.tools.return_value = [{"name": "call_tool"}]
                mock_client.call.return_value = {"content": []}
                mock_client_cls.return_value = mock_client

                res = playtest.run_playtest(proj, duration=1)
                self.assertEqual(res["status"], "completed")
                self.assertTrue(res["evaluation"]["clean_run"], "No errors detected is a clean run")
                self.assertFalse(res["evaluation"]["gameplay_verified"], "Gameplay must not be verified without signals")
                self.assertFalse(res["verification"]["gameplay_acceptance_passed"])

    def test_stop_failure_records_reason_and_sets_indeterminate(self):
        """Stop failure must be recorded and state must be marked INDETERMINATE."""
        with tempfile.TemporaryDirectory() as temp:
            proj = Path(temp) / "StopFailGame.uproject"
            proj.write_text('{"FileVersion": 3}')

            logs_dir = Path(temp) / "Saved/Logs"
            logs_dir.mkdir(parents=True)
            log_file = logs_dir / "StopFailGame.log"
            log_file.write_text("LogInit: Engine started.\n")

            with patch("playtest.Client") as mock_client_cls, \
                 patch("playtest.time.sleep", return_value=None):
                mock_client = MagicMock()
                mock_client.tools.return_value = [{"name": "call_tool"}]
                # Start succeeds, but Stop fails
                def mock_call(tool_name, arguments):
                    tn = arguments.get("tool_name", "")
                    if tn == "StopPIE" or tn == "stop_pie":
                        return {"content": [{"type": "text", "text": "Editor failed to stop session"}], "isError": True}
                    return {"content": [{"type": "text", "text": '{"returnValue": true}'}]}

                mock_client.call.side_effect = mock_call
                mock_client_cls.return_value = mock_client

                res = playtest.run_playtest(proj, duration=1)
                self.assertEqual(res["status"], "failed")
                self.assertEqual(res["pie_state"], PIEState.INDETERMINATE)
                self.assertFalse(res["verification"]["stop_successful"])
                self.assertIsNotNone(res["verification"]["stop_failure_reason"])


if __name__ == "__main__":
    unittest.main()
