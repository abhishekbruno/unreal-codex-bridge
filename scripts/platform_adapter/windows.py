"""Windows-specific platform adapter for Unreal Engine and Codex."""

import json
import os
from pathlib import Path
import platform
import re
import shutil
import subprocess

from .base import PlatformAdapter


class WindowsAdapter(PlatformAdapter):
    """Adapter for Windows 10/11 operating systems."""

    @property
    def name(self) -> str:
        return "windows"

    def detect_os(self) -> dict:
        return {
            "platform": "windows",
            "system": platform.system(),
            "release": platform.release(),
            "version": platform.version(),
            "machine": platform.machine()
        }

    def detect_architecture(self) -> str:
        mach = platform.machine().lower()
        if mach in ("amd64", "x86_64"):
            return "x86_64"
        if mach in ("arm64", "aarch64"):
            return "arm64"
        return mach

    def discover_engine_installations(self) -> list:
        found = []
        seen_roots = set()

        # 1. Inspect Epic Games Launcher Manifests
        manifest_dir = Path(os.environ.get("PROGRAMDATA", r"C:\ProgramData")) / r"Epic\EpicGamesLauncher\Data\Manifests"
        if manifest_dir.is_dir():
            for item in manifest_dir.glob("*.item"):
                try:
                    data = json.loads(item.read_bytes().decode("utf-8-sig"))
                    app_name = str(data.get("AppName", ""))
                    loc = data.get("InstallLocation")
                    if loc and ("UE_" in app_name or "UnrealEngine" in app_name):
                        engine_path = Path(loc).resolve()
                        if engine_path not in seen_roots and (engine_path / "Engine/Build/Build.version").is_file():
                            seen_roots.add(engine_path)
                            found.append({
                                "version": data.get("AppVersionString", app_name),
                                "path": engine_path,
                                "source": "epic_launcher_manifest"
                            })
                except Exception:
                    continue

        # 2. Check standard installation drives (C, D, E)
        for drive in ("C", "D", "E"):
            candidates = [
                Path(f"{drive}:/UE_5.8"),
                Path(f"{drive}:/UE_5.9"),
                Path(f"{drive}:/Program Files/Epic Games/UE_5.8"),
                Path(f"{drive}:/Program Files/Epic Games/UE_5.9"),
            ]
            for cand in candidates:
                cand_res = cand.resolve()
                if cand_res not in seen_roots and (cand_res / "Engine/Build/Build.version").is_file():
                    seen_roots.add(cand_res)
                    found.append({
                        "version": cand_res.name,
                        "path": cand_res,
                        "source": "standard_directory"
                    })

        return found

    def resolve_engine_root(self, explicit_engine=None, project_path=None) -> Path:
        if explicit_engine:
            explicit_path = Path(explicit_engine).resolve()
            if (explicit_path / "Engine/Build/Build.version").is_file():
                return explicit_path
            raise FileNotFoundError(f"Specified engine path does not contain Engine/Build/Build.version: {explicit_path}")

        env_root = os.environ.get("UE_ENGINE_ROOT")
        if env_root:
            env_path = Path(env_root).resolve()
            if (env_path / "Engine/Build/Build.version").is_file():
                return env_path

        if project_path:
            proj = Path(project_path).resolve()
            try:
                data = self.parse_uproject_descriptor(proj)
                assoc = data.get("EngineAssociation", "")
                associated = self.resolve_associated_engine(proj, assoc)
                if associated:
                    return associated
            except Exception:
                pass

        installs = self.discover_engine_installations()
        if installs:
            return installs[0]["path"]

        # Default fallback
        fallback = Path(r"D:\UE_5.8").resolve()
        if (fallback / "Engine/Build/Build.version").is_file():
            return fallback

        raise FileNotFoundError("Could not discover an installed Unreal Engine root on Windows. Specify --engine explicitly.")

    def resolve_editor_executable(self, engine_root: Path) -> Path:
        root = Path(engine_root).resolve()
        return root / "Engine/Binaries/Win64/UnrealEditor.exe"

    def resolve_codex_binary(self) -> Path:
        for candidate_name in ("codex.cmd", "codex.exe", "codex"):
            found = shutil.which(candidate_name)
            if found:
                return Path(found).resolve()

        appdata = os.environ.get("APPDATA")
        if appdata:
            npm_cmd = Path(appdata) / "npm/codex.cmd"
            if npm_cmd.is_file():
                return npm_cmd

        localappdata = os.environ.get("LOCALAPPDATA")
        if localappdata:
            prog_exe = Path(localappdata) / "Programs/codex/codex.exe"
            if prog_exe.is_file():
                return prog_exe

        raise FileNotFoundError("Codex CLI executable (codex.cmd or codex.exe) not found on PATH or standard npm directories.")

    def inspect_port_owner(self, port: int) -> int | None:
        try:
            output = subprocess.check_output(["netstat", "-ano", "-p", "tcp"], text=True, stderr=subprocess.DEVNULL)
            pattern = re.compile(rf"(?:127\.0\.0\.1|0\.0\.0\.0|\[::1\]|\[::\]):{port}\s+.*LISTENING\s+(\d+)", re.IGNORECASE)
            for line in output.splitlines():
                match = pattern.search(line)
                if match:
                    return int(match.group(1))
        except Exception:
            pass
        return None

    def find_running_editor_processes(self) -> list:
        processes = []
        ps_cmd = (
            "Get-CimInstance Win32_Process -Filter \"Name = 'UnrealEditor.exe'\" | "
            "Select-Object ProcessId, ExecutablePath, CommandLine | ConvertTo-Json -Compress"
        )
        try:
            res = subprocess.run(["powershell", "-NoProfile", "-Command", ps_cmd],
                                 capture_output=True, text=True, timeout=5)
            if res.returncode == 0 and res.stdout.strip():
                raw = res.stdout.strip()
                items = json.loads(raw)
                if isinstance(items, dict):
                    items = [items]
                for item in items:
                    processes.append({
                        "pid": item.get("ProcessId"),
                        "executable": item.get("ExecutablePath"),
                        "cmdline": item.get("CommandLine", "")
                    })
        except Exception:
            pass
        return processes

    def verify_project_identity(self, port: int, project_path: Path, engine_root: Path = None) -> bool:
        pid = self.inspect_port_owner(port)
        if not pid:
            return False

        proj_path = Path(project_path).resolve()
        ps_cmd = f"Get-CimInstance Win32_Process -Filter \"ProcessId = {pid}\" | Select-Object ProcessId, ExecutablePath, CommandLine | ConvertTo-Json -Compress"
        try:
            res = subprocess.run(["powershell", "-NoProfile", "-Command", ps_cmd],
                                 capture_output=True, text=True, timeout=5)
            if res.returncode != 0 or not res.stdout.strip():
                return False
            data = json.loads(res.stdout.strip())
            exe = Path(data.get("ExecutablePath") or "").resolve()
            cmdline = str(data.get("CommandLine") or "")

            if exe.name.lower() != "unrealeditor.exe":
                return False

            if engine_root:
                expected_bin = self.resolve_editor_executable(Path(engine_root))
                if exe != expected_bin.resolve():
                    return False

            # Check if project path is in command line
            norm_proj_str = str(proj_path).lower()
            norm_proj_fwd = str(proj_path).replace("\\", "/").lower()
            cmd_lower = cmdline.lower()

            if norm_proj_str in cmd_lower or norm_proj_fwd in cmd_lower:
                return True

            # Check if project stem matches if command line used relative path
            if f'"{proj_path.stem}.uproject"' in cmd_lower or f"'{proj_path.stem}.uproject'" in cmd_lower:
                return True

        except Exception:
            return False

        return False

    def check_toolchain_prerequisites(self) -> dict:
        result = {"has_compiler": False, "compiler_path": None, "details": []}
        cl_path = shutil.which("cl.exe")
        if cl_path:
            result["has_compiler"] = True
            result["compiler_path"] = str(Path(cl_path).resolve())
            result["details"].append("MSVC cl.exe detected on PATH.")

        vswhere = Path(os.environ.get("ProgramFiles(x86)", r"C:\Program Files (x86)")) / r"Microsoft Visual Studio\Installer\vswhere.exe"
        if vswhere.is_file():
            result["details"].append("Visual Studio Installer (vswhere) present.")

        return result
