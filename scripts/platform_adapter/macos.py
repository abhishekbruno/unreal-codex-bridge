"""macOS-specific platform adapter for Unreal Engine and Codex (Apple Silicon & Intel)."""

import json
import os
from pathlib import Path
import platform
import re
import shutil
import subprocess

from .base import PlatformAdapter


class MacOSAdapter(PlatformAdapter):
    """Adapter for macOS operating systems (supports arm64 Apple Silicon and x86_64 Intel)."""

    MAC_BINARY_REL = Path("Engine/Binaries/Mac/UnrealEditor.app/Contents/MacOS/UnrealEditor")
    STANDARD_EPIC_ROOT = Path("/Users/Shared/Epic Games")

    @property
    def name(self) -> str:
        return "macos"

    def detect_os(self) -> dict:
        mac_ver = platform.mac_ver()
        return {
            "platform": "macos",
            "system": platform.system(),
            "release": platform.release(),
            "version": mac_ver[0] or platform.version(),
            "machine": platform.machine(),
            "is_apple_silicon": platform.machine().lower() in ("arm64", "aarch64")
        }

    def detect_architecture(self) -> str:
        mach = platform.machine().lower()
        if mach in ("arm64", "aarch64"):
            return "arm64"
        if mach in ("x86_64", "amd64", "i386"):
            return "x86_64"
        return mach

    def discover_engine_installations(self) -> list:
        found = []
        seen_roots = set()

        # 1. Inspect standard Epic Games Launcher directory
        if self.STANDARD_EPIC_ROOT.is_dir():
            for ue_dir in sorted(self.STANDARD_EPIC_ROOT.glob("UE_*")):
                exe = ue_dir / self.MAC_BINARY_REL
                if ue_dir not in seen_roots and exe.is_file():
                    seen_roots.add(ue_dir)
                    found.append({
                        "version": ue_dir.name,
                        "path": ue_dir,
                        "source": "epic_launcher_standard"
                    })

        # 2. Inspect common user checkout / source locations
        common_candidates = [
            Path.home() / "unreal",
            Path.home() / "UnrealEngine",
            Path("/opt/unreal"),
            Path("/opt/UnrealEngine"),
        ]
        for cand in common_candidates:
            if cand.is_dir() and cand not in seen_roots:
                exe = cand / self.MAC_BINARY_REL
                if exe.is_file() and (cand / "Engine/Build/Build.version").is_file():
                    seen_roots.add(cand)
                    found.append({
                        "version": cand.name,
                        "path": cand,
                        "source": "user_source_build"
                    })

        return found

    def resolve_engine_root(self, explicit_engine=None, project_path=None) -> Path:
        if explicit_engine:
            explicit_path = Path(explicit_engine).expanduser().resolve()
            exe = explicit_path / self.MAC_BINARY_REL
            if exe.is_file() or (explicit_path / "Engine/Build/Build.version").is_file():
                return explicit_path
            raise FileNotFoundError(f"Specified macOS engine root does not contain UnrealEditor.app: {explicit_path}")

        env_root = os.environ.get("UE_ENGINE_ROOT")
        if env_root:
            env_path = Path(env_root).expanduser().resolve()
            if (env_path / self.MAC_BINARY_REL).is_file() or (env_path / "Engine/Build/Build.version").is_file():
                return env_path

        if project_path:
            proj = Path(project_path).expanduser().resolve()
            try:
                data = self.parse_uproject_descriptor(proj)
                assoc = data.get("EngineAssociation", "")
                associated = self.resolve_associated_engine(proj, assoc)
                if associated and (associated / self.MAC_BINARY_REL).is_file():
                    return associated
                if re.fullmatch(r"\d+\.\d+(?:\.\d+)?", assoc):
                    release = ".".join(assoc.split(".")[:2])
                    cand = self.STANDARD_EPIC_ROOT / ("UE_" + release)
                    if cand.is_dir() and (cand / self.MAC_BINARY_REL).is_file():
                        return cand
            except Exception:
                pass

        installs = self.discover_engine_installations()
        if installs:
            return installs[0]["path"]

        # Default fallback path
        fallback = self.STANDARD_EPIC_ROOT / "UE_5.8"
        if (fallback / self.MAC_BINARY_REL).is_file():
            return fallback

        raise FileNotFoundError("Could not discover a valid macOS Unreal Engine installation under /Users/Shared/Epic Games. Specify --engine explicitly.")

    def resolve_editor_executable(self, engine_root: Path) -> Path:
        root = Path(engine_root)
        return root / self.MAC_BINARY_REL

    def resolve_codex_binary(self) -> Path:
        # Check PATH for unix codex executable
        found = shutil.which("codex")
        if found and not found.lower().endswith(".cmd") and not found.lower().endswith(".bat"):
            return Path(found)

        # Check standard macOS tool locations
        candidates = [
            Path("/usr/local/bin/codex"),
            Path("/opt/homebrew/bin/codex"),
            Path.home() / ".npm-global/bin/codex",
            Path.home() / ".nvm/current/bin/codex",
        ]
        for cand in candidates:
            if cand.is_file() and os.access(cand, os.X_OK):
                return cand

        raise FileNotFoundError("Codex CLI executable ('codex') not found in PATH or standard macOS bin directories (/opt/homebrew/bin, /usr/local/bin).")

    def inspect_port_owner(self, port: int) -> int | None:
        """Find listening PID using macOS /usr/sbin/lsof."""
        lsof_bin = shutil.which("lsof") or "/usr/sbin/lsof"
        try:
            res = subprocess.run(
                [lsof_bin, "-nP", f"-iTCP:{port}", "-sTCP:LISTEN", "-Fp"],
                capture_output=True, text=True, timeout=5
            )
            if res.returncode == 0 and res.stdout.strip():
                pids = [line[1:].strip() for line in res.stdout.splitlines() if line.startswith("p") and line[1:].strip().isdigit()]
                if pids:
                    return int(pids[0])
        except Exception:
            pass
        return None

    def find_running_editor_processes(self) -> list:
        processes = []
        try:
            res = subprocess.run(["ps", "-eo", "pid,command"], capture_output=True, text=True, timeout=5)
            if res.returncode == 0 and res.stdout:
                for line in res.stdout.splitlines():
                    if "UnrealEditor" in line:
                        parts = line.strip().split(None, 1)
                        if len(parts) >= 2 and parts[0].isdigit():
                            processes.append({
                                "pid": int(parts[0]),
                                "cmdline": parts[1]
                            })
        except Exception:
            pass
        return processes

    def verify_project_identity(self, port: int, project_path: Path, engine_root: Path = None) -> bool:
        """Verify authentic Unreal Editor listener ownership, binary path, and project identity on macOS.

        Requires:
        1. An authentic listening process on the specified port.
        2. Process executable is an authentic UnrealEditor binary inside a macOS application bundle.
        3. Executable matches the expected engine_root when provided.
        4. Reliable project identity verified via .uproject argument matching target project.
        Zero fallback to unverified process names or stale log files.
        """
        pid = self.inspect_port_owner(port)
        if not pid:
            return False

        proj_path = Path(project_path).expanduser().resolve()
        try:
            res = subprocess.run(["ps", "-p", str(pid), "-o", "command="], capture_output=True, text=True, timeout=5)
            if res.returncode != 0 or not res.stdout.strip():
                return False
            cmdline = res.stdout.strip()

            # 1. Extract authentic executable token from command line
            found_exe = None
            if cmdline.strip().startswith('"'):
                m = re.match(r'^\s*"([^"]+)"', cmdline)
                if m:
                    found_exe = m.group(1)
            else:
                m = re.match(r'^\s*(.*?UnrealEditor(?:\.app[/\\]Contents[/\\]MacOS[/\\]UnrealEditor)?)(?:\s+|$)', cmdline, re.IGNORECASE)
                if m:
                    found_exe = m.group(1)
                else:
                    found_exe = cmdline.split()[0]

            if not found_exe:
                return False

            norm_exe = re.sub(r'^[a-zA-Z]:', '', found_exe.replace('\\', '/')).lower()
            exe_basename = Path(norm_exe).name.lower()

            # Binary name must be UnrealEditor (not python, not a shell script)
            if not (exe_basename == "unrealeditor" or exe_basename.startswith("unrealeditor-")):
                return False

            # Require executable to be in Mac application bundle or Engine/Binaries/Mac
            if "unrealeditor.app/contents/macos" not in norm_exe and "engine/binaries/mac" not in norm_exe:
                return False

            # 2. If engine_root specified, verify executable is strictly within expected engine
            if engine_root:
                expected_bin = self.resolve_editor_executable(Path(engine_root))
                norm_expected = re.sub(r'^[a-zA-Z]:', '', str(expected_bin).replace('\\', '/')).lower()
                norm_engine = re.sub(r'^[a-zA-Z]:', '', str(Path(engine_root)).replace('\\', '/')).lower()
                if norm_exe != norm_expected and not norm_exe.startswith(norm_engine):
                    return False

            # 3. Require authentic project argument matching target project
            remainder = cmdline[len(found_exe):]
            proj_matches = re.findall(r'"([^"\r\n]*\.uproject)"|(?:-project=)?([^\s"]*\.uproject)', remainder, re.IGNORECASE)
            if not proj_matches:
                # Also check whole command line in case project path preceded executable or was parsed differently
                proj_matches = re.findall(r'"([^"\r\n]*\.uproject)"|(?:-project=)?([^\s"]*\.uproject)', cmdline, re.IGNORECASE)

            if not proj_matches:
                return False

            found_proj = proj_matches[0][0] or proj_matches[0][1]
            if found_proj.lower().startswith("-project="):
                found_proj = found_proj.split("=", 1)[1].strip('\'"')

            norm_found = re.sub(r'^[a-zA-Z]:', '', found_proj.replace('\\', '/')).lower()
            norm_target = re.sub(r'^[a-zA-Z]:', '', str(proj_path).replace('\\', '/')).lower()

            if norm_found == norm_target:
                return True

            # If relative path supplied on command line, verify filename matches and is relative
            if Path(norm_found).name == Path(norm_target).name and not Path(found_proj).is_absolute():
                return True

        except Exception:
            return False

        return False

    def check_toolchain_prerequisites(self) -> dict:
        result = {"has_compiler": False, "compiler_path": None, "details": []}
        try:
            res = subprocess.run(["xcode-select", "-p"], capture_output=True, text=True, timeout=5)
            if res.returncode == 0 and res.stdout.strip():
                result["details"].append(f"Xcode developer directory: {res.stdout.strip()}")
                clang = shutil.which("clang")
                if clang:
                    result["has_compiler"] = True
                    result["compiler_path"] = str(Path(clang).resolve())
                    result["details"].append("Apple Clang compiler available.")
        except Exception:
            pass
        return result
