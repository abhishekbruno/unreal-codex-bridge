"""Cross-platform abstract base class for Unreal Engine & Codex system integration."""

from abc import ABC, abstractmethod
import json
import os
from pathlib import Path
import re
import socket
import subprocess
import sys


class PlatformAdapter(ABC):
    """Abstract interface for platform-specific Unreal Engine and system operations."""

    @property
    @abstractmethod
    def name(self) -> str:
        """Operating system identifier ('windows' or 'macos')."""
        pass

    @abstractmethod
    def detect_os(self) -> dict:
        """Return operating system name, release, and version details."""
        pass

    @abstractmethod
    def detect_architecture(self) -> str:
        """Return normalized processor architecture ('x86_64', 'arm64', etc.)."""
        pass

    @abstractmethod
    def discover_engine_installations(self) -> list:
        """Discover installed Unreal Engine versions across launcher and standard directories."""
        pass

    @abstractmethod
    def resolve_engine_root(self, explicit_engine=None, project_path=None) -> Path:
        """Resolve engine root directory from explicit argument, project descriptor, or discovery."""
        pass

    @abstractmethod
    def resolve_editor_executable(self, engine_root: Path) -> Path:
        """Resolve the executable path to UnrealEditor for this platform."""
        pass

    @abstractmethod
    def resolve_codex_binary(self) -> Path:
        """Locate the Codex CLI executable on the host system."""
        pass

    @abstractmethod
    def inspect_port_owner(self, port: int) -> int | None:
        """Return the PID owning the given TCP port, or None if unoccupied."""
        pass

    @abstractmethod
    def find_running_editor_processes(self) -> list:
        """Return list of running Unreal Editor process dictionaries."""
        pass

    @abstractmethod
    def verify_project_identity(self, port: int, project_path: Path, engine_root: Path = None) -> bool:
        """Verify that the process listening on port is an authentic Unreal Editor running project_path."""
        pass

    @abstractmethod
    def check_toolchain_prerequisites(self) -> dict:
        """Check compiler and developer toolchain status (MSVC on Windows, Xcode on macOS)."""
        pass

    def parse_uproject_descriptor(self, project_path: Path) -> dict:
        """Parse and validate a .uproject JSON descriptor."""
        path = Path(project_path).resolve()
        if not path.is_file() or path.suffix.lower() != ".uproject":
            raise ValueError(f"Project descriptor not found or invalid extension: {path}")
        raw = path.read_bytes().decode("utf-8-sig")
        data = json.loads(raw)
        if not isinstance(data, dict) or not isinstance(data.get("FileVersion"), int):
            raise ValueError(f"Invalid Unreal project descriptor format: {path}")
        return data

    def resolve_associated_engine(self, project_path: Path, association: str) -> Path | None:
        """Resolve relative EngineAssociation path from .uproject."""
        if not association:
            return None
        clean_assoc = association.replace("\\", "/")
        if "/" in clean_assoc:
            candidate = (project_path.parent / clean_assoc).resolve()
            if (candidate / "Engine/Build/Build.version").is_file():
                return candidate
        return None

    def is_port_in_use(self, port: int, host: str = "127.0.0.1") -> bool:
        """Check if TCP port is currently open on loopback."""
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
            sock.settimeout(1.0)
            return sock.connect_ex((host, port)) == 0

    def launch_editor(self, project_path: Path, engine_root: Path, port: int = 8000, extra_args: list = None) -> dict:
        """Launch Unreal Editor with the designated project and MCP parameters."""
        proj = Path(project_path).resolve()
        engine = Path(engine_root).resolve()
        editor_exe = self.resolve_editor_executable(engine)

        if not editor_exe.is_file():
            raise FileNotFoundError(f"Unreal Editor executable not found: {editor_exe}")

        if self.is_port_in_use(port):
            raise ConnectionError(f"Port {port} is already in use. Please specify a free port or inspect the active editor.")

        cmd = [
            str(editor_exe),
            str(proj),
            "-ModelContextProtocolStartServer",
            f"-ModelContextProtocolPort={port}",
            "-ini:Engine:[HTTPServer.Listeners]:DefaultBindAddress=127.0.0.1"
        ]
        if extra_args:
            cmd.extend(extra_args)

        proc = subprocess.Popen(
            cmd,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            start_new_session=True
        )

        return {
            "status": "launched",
            "pid": proc.pid,
            "executable": str(editor_exe),
            "project": str(proj),
            "port": port,
            "engine": str(engine)
        }
