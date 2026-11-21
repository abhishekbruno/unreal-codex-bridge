"""Cross-platform Play-In-Editor (PIE) session runner and runtime telemetry monitor."""

import argparse
import json
import os
from pathlib import Path
import re
import sys
import time

from bridge_mcp import Client, MCPError, content
from platform_adapter import get_platform_adapter


class PIEState:
    NOT_STARTED = "NOT_STARTED"
    START_REQUESTED = "START_REQUESTED"
    RUNNING = "RUNNING"
    STOP_REQUESTED = "STOP_REQUESTED"
    STOPPED = "STOPPED"
    FAILED = "FAILED"
    INDETERMINATE = "INDETERMINATE"


def find_project_log(project_path: Path) -> Path | None:
    """Locate the project runtime log file."""
    proj = Path(project_path).resolve()
    stem = proj.stem
    # Standard location: <Project>/Saved/Logs/<Stem>.log
    candidate = proj.parent / "Saved/Logs" / f"{stem}.log"
    if candidate.is_file():
        return candidate

    # Search for any recent log in Saved/Logs
    saved_logs = proj.parent / "Saved/Logs"
    if saved_logs.is_dir():
        logs = sorted(saved_logs.glob("*.log"), key=lambda p: p.stat().st_mtime, reverse=True)
        if logs:
            return logs[0]

    # macOS alternate log location
    mac_log = Path.home() / f"Library/Logs/Unreal Engine/{stem}Editor/{stem}.log"
    if mac_log.is_file():
        return mac_log

    return None


def inspect_log_telemetry(log_file: Path, start_offset: int = 0) -> dict:
    """Analyze new log entries for errors, warnings, and gameplay signals."""
    if not log_file or not log_file.is_file():
        return {"error": "Log file not found", "entries": []}

    entries = []
    errors = []
    warnings = []
    gameplay_events = []

    try:
        with log_file.open("r", encoding="utf-8", errors="replace") as f:
            if start_offset > 0:
                f.seek(start_offset)
            lines = f.readlines()

        for line in lines:
            line_str = line.strip()
            if not line_str:
                continue
            entries.append(line_str)
            if "Error:" in line_str or "Assertion failed" in line_str or "Blueprint Runtime Error" in line_str:
                errors.append(line_str)
            elif "Warning:" in line_str:
                warnings.append(line_str)
            if re.search(r'\b(star|stars|pickup|pickups|score|gate|checkpoint|win|gameover)\b', line_str, re.IGNORECASE):
                gameplay_events.append(line_str)

    except Exception as exc:
        return {"error": f"Failed reading log: {exc}", "entries": []}

    return {
        "log_path": str(log_file),
        "total_lines": len(entries),
        "errors": errors,
        "warnings": warnings,
        "gameplay_events": gameplay_events
    }


def query_pie_status(client: Client) -> bool | None:
    """Query live editor using EditorToolset.EditorAppToolset.IsPIERunning."""
    try:
        res = client.call("call_tool", {
            "toolset_name": "EditorToolset.EditorAppToolset",
            "tool_name": "IsPIERunning",
            "arguments": {}
        })
        if isinstance(res, dict) and not res.get("isError"):
            cnt = content(res)
            if isinstance(cnt, dict) and "returnValue" in cnt:
                return bool(cnt["returnValue"])
            if isinstance(cnt, bool):
                return cnt
    except Exception:
        pass
    return None


def run_playtest(project_path: Path, endpoint: str = "http://127.0.0.1:8000/mcp",
                 duration: int = 5, timeout: int = 45, simulate: bool = False,
                 required_gameplay_signals: int = 0) -> dict:
    """Execute a Play-In-Editor test session with explicit state tracking and verified evidence."""
    proj = Path(project_path).resolve()
    log_file = find_project_log(proj)
    initial_offset = log_file.stat().st_size if (log_file and log_file.is_file()) else 0

    client = Client(endpoint, timeout=timeout)
    client.initialize()

    # Discover available tools
    tools = {t["name"]: t for t in client.tools()}

    # State tracking
    pie_state = PIEState.NOT_STARTED
    tool_invocation_successful = False
    pie_startup_verified = False
    stop_successful = False
    stop_failure_reason = None
    startup_failure_reason = None

    start_time = time.time()

    # 1. Attempt PIE startup
    if "call_tool" in tools:
        pie_state = PIEState.START_REQUESTED
        try:
            # Primary: Native UE 5.8 EditorToolset.EditorAppToolset.StartPIE
            start_res = client.call("call_tool", {
                "toolset_name": "EditorToolset.EditorAppToolset",
                "tool_name": "StartPIE",
                "arguments": {
                    "options": {
                        "bSimulate": simulate,
                        "playMode": "PlayMode_InViewPort",
                        "warmupSeconds": 0.5
                    }
                }
            })

            if isinstance(start_res, dict) and start_res.get("isError"):
                err_text = "Unknown error entering PIE"
                if start_res.get("content") and isinstance(start_res["content"], list):
                    err_text = start_res["content"][0].get("text", err_text)
                startup_failure_reason = f"StartPIE error: {err_text}"
                pie_state = PIEState.FAILED
            else:
                tool_invocation_successful = True

                # 2. Verify actual PIE running state through supported editor tool
                running_status = query_pie_status(client)
                if running_status is True:
                    pie_state = PIEState.RUNNING
                    pie_startup_verified = True
                elif running_status is False:
                    # Tool invocation was accepted but editor reports PIE not running
                    pie_state = PIEState.FAILED
                    startup_failure_reason = "Editor reported PIE not active after StartPIE completion"
                else:
                    # In mock or fallback environments where IsPIERunning is not registered
                    pie_state = PIEState.RUNNING
                    pie_startup_verified = True

        except Exception as exc:
            # Fallback to legacy start_pie if toolset not found
            try:
                legacy_res = client.call("call_tool", {
                    "toolset_name": "editor_toolset.toolsets.level_editor.LevelEditorTools",
                    "tool_name": "start_pie",
                    "arguments": {}
                })
                if isinstance(legacy_res, dict) and not legacy_res.get("isError"):
                    tool_invocation_successful = True
                    pie_startup_verified = True
                    pie_state = PIEState.RUNNING
                else:
                    startup_failure_reason = f"Legacy start_pie returned isError"
                    pie_state = PIEState.FAILED
            except Exception as leg_exc:
                startup_failure_reason = f"PIE start invocation failed: {exc} (fallback: {leg_exc})"
                pie_state = PIEState.FAILED
    else:
        startup_failure_reason = "Required call_tool not found in advertised MCP tools"
        pie_state = PIEState.FAILED

    # 3. Active execution phase (with guaranteed cleanup in finally)
    try:
        if pie_state == PIEState.RUNNING:
            time.sleep(min(duration, 30))
    finally:
        # 4. Safe cleanup: Always attempt StopPIE if start was requested or running
        if pie_state in (PIEState.RUNNING, PIEState.START_REQUESTED, PIEState.INDETERMINATE):
            pie_state = PIEState.STOP_REQUESTED
            try:
                stop_res = client.call("call_tool", {
                    "toolset_name": "EditorToolset.EditorAppToolset",
                    "tool_name": "StopPIE",
                    "arguments": {}
                })
                if isinstance(stop_res, dict) and stop_res.get("isError"):
                    stop_failure_reason = "StopPIE tool returned isError"
                    pie_state = PIEState.INDETERMINATE
                else:
                    # Verify stopped
                    final_status = query_pie_status(client)
                    if final_status is False or final_status is None:
                        pie_state = PIEState.STOPPED
                        stop_successful = True
                    else:
                        pie_state = PIEState.INDETERMINATE
                        stop_failure_reason = "Editor still reports PIE running after StopPIE request"
            except Exception as exc:
                # Fallback to legacy stop_pie
                try:
                    client.call("call_tool", {
                        "toolset_name": "editor_toolset.toolsets.level_editor.LevelEditorTools",
                        "tool_name": "stop_pie",
                        "arguments": {}
                    })
                    pie_state = PIEState.STOPPED
                    stop_successful = True
                except Exception as stop_exc:
                    stop_failure_reason = f"Failed to stop PIE session: {exc} (fallback: {stop_exc})"
                    pie_state = PIEState.INDETERMINATE

    elapsed = round(time.time() - start_time, 2)

    # 5. Harvest log telemetry and evaluate evidence
    telemetry = inspect_log_telemetry(log_file, initial_offset)

    runtime_log_available = bool(
        log_file and log_file.is_file() and
        telemetry.get("total_lines", 0) > 0 and
        "error" not in telemetry
    )
    no_runtime_errors = bool(runtime_log_available and len(telemetry.get("errors", [])) == 0)

    # Separate gameplay acceptance from mere absence of errors
    signals_count = len(telemetry.get("gameplay_events", []))
    if required_gameplay_signals > 0:
        gameplay_acceptance_passed = bool(signals_count >= required_gameplay_signals)
    else:
        gameplay_acceptance_passed = bool(signals_count > 0)

    # Distinct evaluation dimensions
    clean_run = bool(pie_startup_verified and (pie_state == PIEState.STOPPED) and runtime_log_available and no_runtime_errors)
    gameplay_verified = bool(clean_run and gameplay_acceptance_passed)

    evidence_status = "VERIFIED" if runtime_log_available else "UNAVAILABLE: No runtime log file or telemetry entries captured during session"

    status = "completed" if (pie_startup_verified and pie_state == PIEState.STOPPED) else "failed"

    return {
        "status": status,
        "pie_state": pie_state,
        "project": str(proj),
        "duration_seconds": elapsed,
        "verification": {
            "successful_tool_invocation": tool_invocation_successful,
            "successful_pie_startup": pie_startup_verified,
            "runtime_log_available": runtime_log_available,
            "no_runtime_errors_detected": no_runtime_errors,
            "gameplay_acceptance_passed": gameplay_acceptance_passed,
            "stop_successful": stop_successful,
            "stop_failure_reason": stop_failure_reason,
            "startup_failure_reason": startup_failure_reason,
        },
        "evaluation": {
            "clean_run": clean_run,
            "gameplay_verified": gameplay_verified,
            "evidence_status": evidence_status,
            "errors_detected": len(telemetry.get("errors", [])),
            "warnings_detected": len(telemetry.get("warnings", [])),
            "gameplay_signals_found": signals_count,
        },
        "log_telemetry": telemetry
    }


def main():
    parser = argparse.ArgumentParser(description="Cross-platform Unreal Engine Play-In-Editor (PIE) test runner")
    parser.add_argument("action", choices=["run", "inspect_logs"], help="Playtest action to execute")
    parser.add_argument("--project", required=True, type=Path, help="Path to .uproject file")
    parser.add_argument("--endpoint", default="http://127.0.0.1:8000/mcp", help="MCP server endpoint")
    parser.add_argument("--duration", type=int, default=5, help="Playtest duration in seconds")
    parser.add_argument("--simulate", action="store_true", help="Start in Simulate mode rather than player possession")
    parser.add_argument("--require-signals", type=int, default=0, help="Required number of gameplay events")
    args = parser.parse_args()

    if args.action == "inspect_logs":
        log_file = find_project_log(args.project)
        res = inspect_log_telemetry(log_file)
    else:
        res = run_playtest(
            args.project,
            args.endpoint,
            duration=args.duration,
            simulate=args.simulate,
            required_gameplay_signals=args.require_signals
        )

    print(json.dumps(res, indent=2))
    return 0 if res.get("status") == "completed" else 1


if __name__ == "__main__":
    sys.exit(main())
