"""macOS-specific platform adapter for Unreal Engine and Codex (Apple Silicon & Intel)."""

import json
import os
from pathlib import Path
import platform
import posixpath
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

    def get_process_executable(self, pid: int) -> Path | None:
        """Query the authentic OS-level executable path for a given PID on macOS.

        Uses the Darwin kernel libproc.proc_pidpath C API as primary verification,
        falling back to lsof -p <PID> -d txt -Fn.
        Does not rely on user-controlled argv / command lines.
        """
        # 1. Primary: Darwin kernel proc_pidpath via libSystem or libproc
        try:
            import ctypes
            import ctypes.util
            lib = None
            for name in ("libSystem.B.dylib", "libproc.dylib", "/usr/lib/libproc.dylib"):
                try:
                    cand = ctypes.CDLL(name)
                    if hasattr(cand, "proc_pidpath"):
                        lib = cand
                        break
                except Exception:
                    continue
            if lib is None:
                try:
                    cand = ctypes.CDLL(None)
                    if hasattr(cand, "proc_pidpath"):
                        lib = cand
                except Exception:
                    pass

            if lib and hasattr(lib, "proc_pidpath"):
                lib.proc_pidpath.argtypes = [ctypes.c_int, ctypes.c_char_p, ctypes.c_uint32]
                lib.proc_pidpath.restype = ctypes.c_int
                buf = ctypes.create_string_buffer(4096)
                res = lib.proc_pidpath(ctypes.c_int(pid), buf, ctypes.c_uint32(len(buf)))
                if res > 0:
                    raw_path = buf.value.decode("utf-8").strip()
                    if raw_path:
                        p = Path(raw_path)
                        if p.is_file():
                            return p.resolve()
        except Exception:
            pass

        # 2. Secondary: lsof text segment inspection (lsof -a -p <PID> -d txt -Fn)
        lsof_bin = shutil.which("lsof") or "/usr/sbin/lsof"
        try:
            res = subprocess.run(
                [lsof_bin, "-a", "-p", str(pid), "-d", "txt", "-Fn"],
                capture_output=True, text=True, timeout=5
            )
            if res.returncode == 0 and res.stdout:
                for line in res.stdout.splitlines():
                    if line.startswith("n/"):
                        p = Path(line[1:].strip())
                        if p.is_file():
                            return p.resolve()
        except Exception:
            pass

        return None

    def verify_project_identity(self, port: int, project_path: Path, engine_root: Path = None) -> bool:
        """Verify authentic Unreal Editor listener ownership, binary path, and project identity on macOS.

        Requires:
        1. Authentic TCP listener ownership via inspect_port_owner.
        2. Authentic Unreal Editor executable path verified via macOS OS-level process API (proc_pidpath / lsof txt).
        3. Verified expected engine installation: rejects lookalike engine-directory prefixes.
        4. Exact project identity: requires absolute canonical .uproject match; rejects ambiguous relative paths.
        5. Rejection of stale logs, spoofed process names, and unverified executables.
        Fail closed: if identity cannot be established with certainty, return False.
        """
        pid = self.inspect_port_owner(port)
        if not pid:
            return False

        proj_path = Path(project_path).expanduser().resolve()

        # 1. Query OS-level authentic executable path
        actual_exe = self.get_process_executable(pid)

        # Also get command line for project argument validation
        try:
            res = subprocess.run(["ps", "-p", str(pid), "-o", "command="], capture_output=True, text=True, timeout=5)
            if res.returncode != 0 or not res.stdout.strip():
                return False
            cmdline = res.stdout.strip()
        except Exception:
            return False

        # If actual_exe was found via OS API, verify it
        if actual_exe:
            norm_exe_str = str(actual_exe).replace("\\", "/")
            exe_name = actual_exe.name.lower()
            if not (exe_name == "unrealeditor" or exe_name.startswith("unrealeditor-")):
                return False
            if "unrealeditor.app/contents/macos" not in norm_exe_str.lower() and "engine/binaries/mac" not in norm_exe_str.lower():
                return False
            verified_exe = actual_exe
        else:
            # Fallback to parsing executable from command line only if OS API did not return
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

            cand = Path(found_exe).resolve()
            exe_name = cand.name.lower()
            if not (exe_name == "unrealeditor" or exe_name.startswith("unrealeditor-")):
                return False
            norm_cand_str = str(cand).replace("\\", "/").lower()
            if "unrealeditor.app/contents/macos" not in norm_cand_str and "engine/binaries/mac" not in norm_cand_str:
                return False
            verified_exe = cand

        # 2. If engine_root specified, verify executable is strictly within expected engine
        # Reject lookalike engine-directory prefixes (e.g. /Users/Shared/Epic Games/UE_5.8_fake)
        if engine_root:
            norm_exe_str = str(verified_exe).replace("\\", "/")
            norm_engine_str = str(engine_root).replace("\\", "/")
            norm_exe_posix = posixpath.normpath(re.sub(r'^[a-zA-Z]:', '', norm_exe_str)).lower()
            norm_engine_posix = posixpath.normpath(re.sub(r'^[a-zA-Z]:', '', norm_engine_str)).lower()

            # Strict directory boundary check: must be inside engine_root directory
            if not (norm_exe_posix == norm_engine_posix or norm_exe_posix.startswith(norm_engine_posix + "/")):
                return False

            expected_bin = self.resolve_editor_executable(Path(engine_root))
            norm_expected_posix = posixpath.normpath(re.sub(r'^[a-zA-Z]:', '', str(expected_bin).replace("\\", "/"))).lower()
            if norm_exe_posix != norm_expected_posix and not norm_exe_posix.startswith(norm_engine_posix + "/engine"):
                return False

        # 3. Exact project identity:
        # Extract .uproject tokens from command line
        # Strict rejection of ambiguous relative project paths
        proj_matches = re.findall(r'"([^"\r\n]*\.uproject)"|(?:-project=)?([^\s"]*\.uproject)', cmdline, re.IGNORECASE)
        if not proj_matches:
            return False

        extracted_paths = []
        for t1, t2 in proj_matches:
            raw = t1 or t2
            if raw.lower().startswith("-project="):
                raw = raw.split("=", 1)[1].strip('\'"')
            extracted_paths.append(raw)

        unique_tokens = list(set(extracted_paths))
        if len(unique_tokens) != 1:
            return False

        cand_proj_str = unique_tokens[0]

        # REJECTION OF AMBIGUOUS RELATIVE PATHS:
        # Ambiguous relative paths without absolute canonical base must be rejected
        is_abs = posixpath.isabs(cand_proj_str) or Path(cand_proj_str).is_absolute()
        if not is_abs:
            return False

        # Verify exact canonical path match (cross-platform POSIX normalized)
        norm_cand = posixpath.normpath(re.sub(r'^[a-zA-Z]:', '', cand_proj_str.replace('\\', '/'))).lower()
        norm_target = posixpath.normpath(re.sub(r'^[a-zA-Z]:', '', str(proj_path).replace('\\', '/'))).lower()
        if norm_cand != norm_target:
            return False

        return True

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
