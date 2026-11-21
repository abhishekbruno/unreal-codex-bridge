"""Cross-platform Unreal Engine editor lifecycle CLI for Windows 10/11 and macOS.

Provides consistent subcommands: detect, prepare, launch, connect, doctor, status, uninstall.
"""

import argparse
import json
import os
from pathlib import Path
import sys

# Ensure scripts directory is on sys.path
SCRIPTS_DIR = Path(__file__).resolve().parent
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

from platform_adapter import get_platform_adapter, PlatformNotSupportedError
from bridge_mcp import Client, MCPError
import configure
import doctor


def cmd_detect(args, adapter):
    """Detect platform, architecture, installed Unreal Engines, and nearby projects."""
    os_info = adapter.detect_os()
    arch = adapter.detect_architecture()
    engines = adapter.discover_engine_installations()
    toolchain = adapter.check_toolchain_prerequisites()

    # Discover nearby .uproject files
    search_root = Path(args.search_dir or os.getcwd()).resolve()
    projects = []
    try:
        for p in search_root.rglob("*.uproject"):
            if "Saved" not in p.parts and "Intermediate" not in p.parts:
                projects.append(str(p))
                if len(projects) >= 20:
                    break
    except Exception:
        pass

    codex_bin = None
    try:
        codex_bin = str(adapter.resolve_codex_binary())
    except Exception as exc:
        codex_bin = f"Not detected ({exc})"

    return {
        "platform": os_info,
        "architecture": arch,
        "codex_binary": codex_bin,
        "toolchain": toolchain,
        "installed_engines": [{"version": e["version"], "path": str(e["path"]), "source": e["source"]} for e in engines],
        "discovered_projects": projects
    }


def cmd_prepare(args, adapter):
    """Validate and configure Unreal project settings with backup."""
    if not args.project:
        raise ValueError("Specify --project <path/to/Project.uproject>")
    proj = Path(args.project).resolve()
    engine = adapter.resolve_engine_root(args.engine, proj)

    # Use configure.py functions to apply backed-up changes
    uproj_changed = False
    uproj_backup = None

    # Enable plugins in .uproject
    raw_desc = proj.read_bytes().decode("utf-8-sig")
    new_desc = configure.plugin_content(raw_desc)
    if new_desc != raw_desc:
        uproj_backup = configure.backup(proj)
        proj.write_text(new_desc, encoding="utf-8")
        uproj_changed = True

    # Configure DefaultEngine.ini loopback binding
    engine_ini = proj.parent / "Config/DefaultEngine.ini"
    engine_changed = False
    engine_backup = None
    if engine_ini.exists():
        raw_ini = configure.read(engine_ini)
        # Verify no unsafe listener overrides
        configure.guard_listener_overrides([engine_ini], args.port)
        if "[HTTPServer.Listeners]" not in raw_ini:
            engine_backup = configure.backup(engine_ini)
            addition = "\n[HTTPServer.Listeners]\nDefaultBindAddress=127.0.0.1\n"
            engine_ini.write_text(raw_ini + addition, encoding="utf-8")
            engine_changed = True

    # Configure auto-start in DefaultEditorPerProjectUserSettings.ini
    user_ini = proj.parent / "Config/DefaultEditorPerProjectUserSettings.ini"
    user_changed = False
    user_backup = None
    if not user_ini.exists() or "[/Script/ModelContextProtocolEngine.ModelContextProtocolSettings]" not in configure.read(user_ini):
        user_ini.parent.mkdir(parents=True, exist_ok=True)
        raw_user = configure.read(user_ini) if user_ini.exists() else ""
        user_backup = configure.backup(user_ini) if user_ini.exists() else None
        mcp_cfg = (
            "\n[/Script/ModelContextProtocolEngine.ModelContextProtocolSettings]\n"
            "bAutoStartServer=True\n"
            f"ServerPortNumber={args.port}\n"
            "ServerUrlPath=/mcp\n"
        )
        user_ini.write_text(raw_user + mcp_cfg, encoding="utf-8")
        user_changed = True

    return {
        "status": "prepared",
        "project": str(proj),
        "engine": str(engine),
        "uproject_modified": uproj_changed,
        "uproject_backup": str(uproj_backup) if uproj_backup else None,
        "engine_ini_modified": engine_changed,
        "engine_ini_backup": str(engine_backup) if engine_backup else None,
        "user_ini_modified": user_changed,
        "user_ini_backup": str(user_backup) if user_backup else None,
    }


def cmd_launch(args, adapter):
    """Launch Unreal Editor with designated project."""
    if not args.project:
        raise ValueError("Specify --project <path/to/Project.uproject>")
    proj = Path(args.project).resolve()
    engine = adapter.resolve_engine_root(args.engine, proj)
    return adapter.launch_editor(proj, engine, port=args.port)


def cmd_connect(args, adapter):
    """Establish and verify MCP connection to running Unreal Editor."""
    endpoint = f"http://127.0.0.1:{args.port}/mcp"
    if not adapter.is_port_in_use(args.port):
        raise ConnectionError(f"No process listening on port {args.port}. Launch Unreal Editor first.")

    proj = Path(args.project).resolve() if args.project else None
    if proj:
        engine = adapter.resolve_engine_root(args.engine, proj)
        is_verified = adapter.verify_project_identity(args.port, proj, engine)
        if not is_verified:
            raise ConnectionError(f"Process on port {args.port} does not match target project: {proj}")

    client = Client(endpoint, timeout=args.timeout)
    init_res = client.initialize()
    tools = client.tools()

    return {
        "status": "connected",
        "endpoint": endpoint,
        "server_info": init_res.get("serverInfo", {}),
        "protocol_version": init_res.get("protocolVersion"),
        "tool_count": len(tools),
        "tools": [t["name"] for t in tools[:10]]
    }


def cmd_doctor(args, adapter):
    """Run cross-platform diagnostics and MCP integrity checks."""
    proj = Path(args.project).resolve() if args.project else None
    engine = adapter.resolve_engine_root(args.engine, proj)
    endpoint = f"http://127.0.0.1:{args.port}/mcp"
    report = doctor.run(proj, engine, endpoint, full=args.full)
    return report


def cmd_status(args, adapter):
    """Display comprehensive status of engine, editor, project, and MCP."""
    proj = Path(args.project).resolve() if args.project else None
    engine = adapter.resolve_engine_root(args.engine, proj)
    editor_exe = adapter.resolve_editor_executable(engine)
    is_listening = adapter.is_port_in_use(args.port)
    port_owner = adapter.inspect_port_owner(args.port) if is_listening else None

    status_data = {
        "platform": adapter.detect_os(),
        "architecture": adapter.detect_architecture(),
        "project": str(proj) if proj else None,
        "engine": str(engine),
        "editor_executable": str(editor_exe),
        "editor_exists": editor_exe.is_file(),
        "port": args.port,
        "is_listening": is_listening,
        "listener_pid": port_owner
    }

    if is_listening:
        try:
            conn = cmd_connect(args, adapter)
            status_data["mcp_status"] = "operational"
            status_data["mcp_tool_count"] = conn.get("tool_count")
        except Exception as exc:
            status_data["mcp_status"] = f"unreachable: {exc}"
    else:
        status_data["mcp_status"] = "offline"

    return status_data


def cmd_uninstall(args, adapter):
    """Safely revert integration configuration."""
    if not args.project:
        raise ValueError("Specify --project <path/to/Project.uproject>")
    proj = Path(args.project).resolve()
    # Check .codex/config.toml
    codex_toml = proj.parent / ".codex/config.toml"
    reverted = False
    if codex_toml.is_file():
        text = configure.read(codex_toml)
        if "[mcp_servers.unreal-mcp]" in text:
            # Revert using backup
            configure.backup(codex_toml)
            # Remove server section
            import re
            cleaned = re.sub(r'\[mcp_servers\.unreal-mcp\]\s*url\s*=\s*"[^"]+"\s*', '', text)
            codex_toml.write_text(cleaned.strip() + "\n", encoding="utf-8")
            reverted = True

    return {
        "status": "uninstalled",
        "project": str(proj),
        "codex_config_reverted": reverted
    }


def main():
    parser = argparse.ArgumentParser(description="Cross-platform Unreal Engine Editor Lifecycle Manager")
    parser.add_argument("--platform", choices=["windows", "macos"], default=None,
                        help="Force a specific platform adapter for testing")
    subparsers = parser.add_subparsers(dest="action", required=True)

    # detect
    p_detect = subparsers.add_parser("detect", help="Discover platform, engines, and projects")
    p_detect.add_argument("--search-dir", help="Base directory to search for projects")

    # prepare
    p_prepare = subparsers.add_parser("prepare", help="Prepare project descriptor and INI settings")
    p_prepare.add_argument("--project", required=True, help="Path to .uproject file")
    p_prepare.add_argument("--engine", help="Explicit path to Unreal Engine root")
    p_prepare.add_argument("--port", type=int, default=8000, help="MCP listener port")

    # launch
    p_launch = subparsers.add_parser("launch", help="Launch Unreal Editor with target project")
    p_launch.add_argument("--project", required=True, help="Path to .uproject file")
    p_launch.add_argument("--engine", help="Explicit path to Unreal Engine root")
    p_launch.add_argument("--port", type=int, default=8000, help="MCP listener port")

    # connect
    p_connect = subparsers.add_parser("connect", help="Verify and connect to running MCP server")
    p_connect.add_argument("--project", help="Path to target .uproject file for identity verification")
    p_connect.add_argument("--engine", help="Explicit path to Unreal Engine root")
    p_connect.add_argument("--port", type=int, default=8000, help="MCP listener port")
    p_connect.add_argument("--timeout", type=int, default=15, help="Connection timeout in seconds")

    # doctor
    p_doctor = subparsers.add_parser("doctor", help="Run comprehensive preflight diagnostics")
    p_doctor.add_argument("--project", required=True, help="Path to .uproject file")
    p_doctor.add_argument("--engine", help="Explicit path to Unreal Engine root")
    p_doctor.add_argument("--port", type=int, default=8000, help="MCP listener port")
    p_doctor.add_argument("--full", action="store_true", help="Include active level inspection")

    # status
    p_status = subparsers.add_parser("status", help="Query editor and MCP runtime status")
    p_status.add_argument("--project", help="Path to .uproject file")
    p_status.add_argument("--engine", help="Explicit path to Unreal Engine root")
    p_status.add_argument("--port", type=int, default=8000, help="MCP listener port")
    p_status.add_argument("--timeout", type=int, default=10, help="Connection timeout in seconds")

    # uninstall
    p_uninstall = subparsers.add_parser("uninstall", help="Safely remove integration configuration")
    p_uninstall.add_argument("--project", required=True, help="Path to .uproject file")

    args = parser.parse_args()

    try:
        adapter = get_platform_adapter(force_platform=args.platform)
    except PlatformNotSupportedError as err:
        print(json.dumps({"error": str(err)}, indent=2))
        return 2

    handlers = {
        "detect": cmd_detect,
        "prepare": cmd_prepare,
        "launch": cmd_launch,
        "connect": cmd_connect,
        "doctor": cmd_doctor,
        "status": cmd_status,
        "uninstall": cmd_uninstall
    }

    try:
        result = handlers[args.action](args, adapter)
        print(json.dumps(result, indent=2, default=str))
        if args.action == "doctor" and result.get("checks"):
            return doctor.result_code(result["checks"])
        return 0
    except Exception as exc:
        print(json.dumps({"error": str(exc)}, indent=2), file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
