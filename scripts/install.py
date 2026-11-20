#!/usr/bin/env python3
"""Install Codex skills, a local plugin marketplace entry, and MCP config for an Unreal project.

Requires Python >=3.9 and only the standard library. Does not install Unreal/Codex/npm.
"""
import argparse
import json
import re
import shutil
import sys
from datetime import datetime
from pathlib import Path

BUNDLE = Path(__file__).resolve().parents[1]
PLUGIN_NAME = "unreal-codex"
BUNDLE_FILES = ("plugin.json", "mcp.json", "LICENSE")
SKILL_NAMES = ("unreal-mcp", "create-toolset", "unreal-skill")
START_MARKER = "<!-- unreal-codex-start -->"
END_MARKER = "<!-- unreal-codex-end -->"


def write_text_if_changed(path: Path, content: str) -> bool:
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists() and path.read_text(encoding="utf-8") == content:
        return False
    path.write_text(content, encoding="utf-8")
    return True


def enable_project_plugins(uproject: Path) -> bool:
    with uproject.open(encoding="utf-8-sig") as f:
        data = json.load(f)
    if not isinstance(data, dict):
        raise ValueError("Project .uproject must contain a JSON object")
    plugins = data.setdefault("Plugins", [])
    if not isinstance(plugins, list):
        raise ValueError("Expected a Plugins JSON array in .uproject")
    changed = False
    for name in ("ModelContextProtocol", "AllToolsets"):
        existing = next((p for p in plugins if isinstance(p, dict) and p.get("Name") == name), None)
        if existing is None:
            plugins.append({"Name": name, "Enabled": True})
            changed = True
        elif existing.get("Enabled") is not True:
            existing["Enabled"] = True
            changed = True
    if changed:
        stamp = datetime.now().strftime("%Y%m%d-%H%M%S-%f")
        backup = uproject.with_name(uproject.name + f".backup-{stamp}")
        shutil.copy2(uproject, backup)
        uproject.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        print(f"  Enabled Unreal MCP and AllToolsets; backup: {backup}")
    return changed


def enable_autostart(project_dir: Path, port: int) -> None:
    ini = project_dir / "Saved" / "Config" / "WindowsEditor" / "EditorPerProjectUserSettings.ini"
    header = "[/Script/ModelContextProtocolEngine.ModelContextProtocolSettings]"
    existing = ini.read_text(encoding="utf-8-sig") if ini.exists() else ""
    lines = existing.splitlines(keepends=True)
    target_index = next((i for i, line in enumerate(lines) if line.strip() == header), None)
    if target_index is None:
        if existing and not existing.endswith(("\n", "\r")):
            existing += "\n"
        existing += f"\n{header}\nbAutoStartServer=True\nServerPortNumber={port}\nServerUrlPath=/mcp\n"
        write_text_if_changed(ini, existing)
        return
    end = next((j for j in range(target_index+1, len(lines)) if lines[j].strip().startswith("[")), len(lines))
    group = "".join(lines[target_index+1:end])
    for key, value in (("bAutoStartServer", "True"), ("ServerPortNumber", str(port)), ("ServerUrlPath", "/mcp")):
        pattern = re.compile(rf"(?m)^\s*{re.escape(key)}\s*=\s*[^\r\n]*$")
        replacement = f"{key}={value}"
        if pattern.search(group):
            group = pattern.sub(replacement, group, count=1)
        else:
            if group and not group.endswith("\n"):
                group += "\n"
            group += replacement + "\n"
    write_text_if_changed(ini, "".join(lines[:target_index+1]) + group + "".join(lines[end:]))


def install_plugin_files(project_dir: Path, port: int) -> None:
    dst = project_dir / ".codex-plugins" / PLUGIN_NAME
    dst.mkdir(parents=True, exist_ok=True)
    for name in BUNDLE_FILES:
        payload = (BUNDLE / name).read_text(encoding="utf-8")
        if name == "mcp.json":
            data = json.loads(payload)
            data["mcpServers"]["unreal-mcp"]["url"] = f"http://127.0.0.1:{port}/mcp"
            payload = json.dumps(data, indent=2, ensure_ascii=False) + "\n"
        write_text_if_changed(dst / name, payload)
    for skill in SKILL_NAMES:
        src = BUNDLE / "skills" / skill
        dest = dst / "skills" / skill
        shutil.copytree(src, dest, dirs_exist_ok=True)


def merge_marketplace(project_dir: Path) -> str:
    path = project_dir / ".agents" / "plugins" / "marketplace.json"
    if path.exists():
        data = json.loads(path.read_text(encoding="utf-8-sig"))
        if not isinstance(data, dict):
            raise ValueError("Existing marketplace must be a JSON object")
    else:
        data = {"name": "unreal-local", "interface": {"displayName": "Local Unreal Tools"}, "plugins": []}
    name = data.get("name", "unreal-local")
    if not isinstance(name, str) or not name:
        raise ValueError("Existing marketplace is missing a valid name")
    plugins = data.setdefault("plugins", [])
    if not isinstance(plugins, list):
        raise ValueError("Existing marketplace.plugins must be an array")
    desired = {
        "name": PLUGIN_NAME,
        "source": {"source": "local", "path": "./.codex-plugins/unreal-codex"},
        "policy": {"installation": "AVAILABLE", "authentication": "ON_INSTALL"},
        "category": "Developer Tools",
    }
    index = next((i for i, p in enumerate(plugins) if isinstance(p, dict) and p.get("name") == PLUGIN_NAME), None)
    if index is None:
        plugins.append(desired)
    else:
        plugins[index] = desired
    write_text_if_changed(path, json.dumps(data, indent=2, ensure_ascii=False) + "\n")
    return name


def update_toml_section(document: str, section: str, settings: dict) -> str:
    """Preserve unrelated TOML and comments; touch only keys in the specified table.

    The section ends at the next TOML table (including its subtables). This function
    intentionally avoids altering nested tool approval tables.
    """
    match_header = re.compile(r"(?m)^\s*\[([^\]\r\n]+)\]\s*(?:#.*)?$")
    matches = list(match_header.finditer(document))
    target = next((i for i, m in enumerate(matches) if m.group(1).strip() == section), None)
    if target is None:
        spacer = "\n" if document.endswith("\n") else "\n\n"
        body = "".join(f"{key} = {value}\n" for key, value in settings.items())
        return document + spacer + f"[{section}]\n" + body
    header = matches[target]
    start = header.end()
    end = matches[target+1].start() if target+1 < len(matches) else len(document)
    body = document[start:end]
    for key, value in settings.items():
        pattern = re.compile(rf"(?m)^\s*{re.escape(key)}\s*=\s*[^\r\n]*$")
        replacement = f"{key} = {value}"
        if pattern.search(body):
            body = pattern.sub(replacement, body, count=1)
        else:
            if body and not body.endswith("\n"):
                body += "\n"
            body += replacement + "\n"
    return document[:start] + body + document[end:]


def merge_codex_config(project_dir: Path, port: int, marketplace: str) -> None:
    config = project_dir / ".codex" / "config.toml"
    content = config.read_text(encoding="utf-8-sig") if config.exists() else ""
    content = update_toml_section(content, "mcp_servers.unreal-mcp", {
        "url": f'"http://127.0.0.1:{port}/mcp"',
        "default_tools_approval_mode": '"writes"',
        "startup_timeout_sec": "30",
        "tool_timeout_sec": "120",
    })
    content = update_toml_section(content, f'plugins."{PLUGIN_NAME}@{marketplace}"', {"enabled": "true"})
    write_text_if_changed(config, content)


def merge_agent_guidance(project_dir: Path) -> None:
    agents = project_dir / "AGENTS.md"
    content = agents.read_text(encoding="utf-8-sig") if agents.exists() else ""
    if START_MARKER in content:
        return
    guidance = (BUNDLE / "AGENTS.unreal-codex.md").read_text(encoding="utf-8")
    suffix = f"\n{START_MARKER}\n{guidance.strip()}\n{END_MARKER}\n"
    write_text_if_changed(agents, content.rstrip() + "\n" + suffix)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project", required=True, help="Absolute or relative path to a .uproject file")
    parser.add_argument("--port", type=int, default=8000, help="Unreal MCP listening port (default 8000)")
    parser.add_argument("--no-autostart", action="store_true", help="Do not alter per-user Unreal MCP auto-start settings")
    args = parser.parse_args()
    if not 1024 <= args.port <= 65535:
        parser.error("--port must be from 1024 to 65535")
    uproject = Path(args.project).expanduser().resolve()
    if not uproject.is_file() or uproject.suffix.lower() != ".uproject":
        parser.error("--project must point to an existing .uproject file")
    if not (BUNDLE / "plugin.json").exists():
        parser.error("run this installer inside the extracted package")
    project_dir = uproject.parent
    print(f"Installing Codex <-> Unreal integration for: {uproject}")
    try:
        enable_project_plugins(uproject)
        if not args.no_autostart:
            enable_autostart(project_dir, args.port)
        install_plugin_files(project_dir, args.port)
        market_name = merge_marketplace(project_dir)
        merge_codex_config(project_dir, args.port, market_name)
        merge_agent_guidance(project_dir)
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
    print("Installed project plugin package, skills, marketplace, Codex MCP config, and AGENTS.md guidance.")
    print("NEXT (Windows, UE 5.9): install Node/Codex CLI if needed; run `codex login` and")
    print("`npm install -g @agentclientprotocol/codex-acp`. Restart the Unreal Editor.")
    print("In Edit > Plugins ensure Unreal Assistant and Unreal MCP/All Toolsets are active.")
    print("In Edit > Editor Preferences > Unreal Assistant > External Agent select Codex and enable it.")
    print("For external Codex, launch from the project directory and inspect `/mcp`.")
    print("Run `python scripts/doctor.py --project <path-to.uproject> --port <port>` after launch.")
    print("SECURITY: keep port 8000 bound to localhost; back up/commit before bulk editor changes.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
