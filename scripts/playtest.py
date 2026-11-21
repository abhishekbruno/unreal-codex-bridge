"""Cross-platform Play-In-Editor (PIE) session runner and runtime telemetry monitor."""

import argparse
import json
import os
from pathlib import Path
import re
import sys
import time

from bridge_mcp import Client, MCPError
from platform_adapter import get_platform_adapter


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


def run_playtest(project_path: Path, endpoint: str = "http://127.0.0.1:8000/mcp",
                 duration: int = 10, timeout: int = 45) -> dict:
    """Execute a Play-In-Editor test session, capture runtime logs, and evaluate results."""
    proj = Path(project_path).resolve()
    log_file = find_project_log(proj)
    initial_offset = log_file.stat().st_size if (log_file and log_file.is_file()) else 0

    client = Client(endpoint, timeout=timeout)
    client.initialize()

    # Discover available tools
    tools = {t["name"]: t for t in client.tools()}
    pie_started = False
    failure_reason = None

    # Attempt to start PIE
    try:
        if "call_tool" in tools:
            try:
                res = client.call("call_tool", {
                    "toolset_name": "editor_toolset.toolsets.level_editor.LevelEditorTools",
                    "tool_name": "start_pie",
                    "arguments": {}
                })
                # Validate MCP tool response
                if isinstance(res, dict) and res.get("isError"):
                    err_msg = "Unknown error entering PIE"
                    if res.get("content") and isinstance(res["content"], list):
                        err_msg = res["content"][0].get("text", err_msg)
                    failure_reason = f"start_pie tool error: {err_msg}"
                else:
                    pie_started = True
            except Exception as exc:
                failure_reason = f"start_pie invocation error: {exc}"
        else:
            failure_reason = "Required call_tool not found in advertised MCP tools"
    except Exception as exc:
        failure_reason = f"Tool discovery failed: {exc}"

    # Wait designated playtest duration while sampling logs
    start_time = time.time()
    if pie_started:
        time.sleep(min(duration, 30))
    elapsed = round(time.time() - start_time, 2)

    # Attempt to stop PIE
    if pie_started and "call_tool" in tools:
        try:
            client.call("call_tool", {
                "toolset_name": "editor_toolset.toolsets.level_editor.LevelEditorTools",
                "tool_name": "stop_pie",
                "arguments": {}
            })
        except Exception:
            pass

    # Harvest log telemetry
    telemetry = inspect_log_telemetry(log_file, initial_offset)

    # Validate runtime evidence availability
    evidence_available = bool(
        log_file and log_file.is_file() and
        telemetry.get("total_lines", 0) > 0 and
        "error" not in telemetry
    )
    evidence_status = "VERIFIED" if evidence_available else "UNAVAILABLE: No runtime log file or telemetry entries captured during session"

    status = "completed" if pie_started else "failed"
    clean_run = bool(pie_started and evidence_available and len(telemetry.get("errors", [])) == 0)

    return {
        "status": status,
        "project": str(proj),
        "pie_invoked": pie_started,
        "failure_reason": failure_reason,
        "duration_seconds": elapsed,
        "log_telemetry": telemetry,
        "evaluation": {
            "clean_run": clean_run,
            "evidence_status": evidence_status,
            "errors_detected": len(telemetry.get("errors", [])),
            "warnings_detected": len(telemetry.get("warnings", [])),
            "gameplay_signals_found": len(telemetry.get("gameplay_events", []))
        }
    }


def main():
    parser = argparse.ArgumentParser(description="Cross-platform Unreal Engine Play-In-Editor (PIE) test runner")
    parser.add_argument("action", choices=["run", "inspect_logs"], help="Playtest action to execute")
    parser.add_argument("--project", required=True, type=Path, help="Path to .uproject file")
    parser.add_argument("--endpoint", default="http://127.0.0.1:8000/mcp", help="MCP server endpoint")
    parser.add_argument("--duration", type=int, default=10, help="Playtest duration in seconds")
    args = parser.parse_args()

    if args.action == "inspect_logs":
        log_file = find_project_log(args.project)
        res = inspect_log_telemetry(log_file)
    else:
        res = run_playtest(args.project, args.endpoint, args.duration)

    print(json.dumps(res, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
