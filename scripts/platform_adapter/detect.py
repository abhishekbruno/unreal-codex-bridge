"""Platform detection and factory for Unreal Codex Bridge."""

import platform
from .base import PlatformAdapter
from .windows import WindowsAdapter
from .macos import MacOSAdapter


class PlatformNotSupportedError(RuntimeError):
    """Raised when the host operating system is neither Windows nor macOS."""
    pass


def detect_system() -> str:
    """Return 'windows' or 'macos' based on the host operating system."""
    sys_name = platform.system().lower()
    if sys_name == "windows":
        return "windows"
    if sys_name == "darwin":
        return "macos"
    raise PlatformNotSupportedError(
        f"Unreal Codex Bridge supports Windows and macOS. Detected unsupported system: {platform.system()!r}"
    )


def get_platform_adapter(force_platform: str = None) -> PlatformAdapter:
    """Return the appropriate PlatformAdapter instance for the current or specified system."""
    chosen = (force_platform.lower() if force_platform else detect_system())
    if chosen == "windows":
        return WindowsAdapter()
    if chosen == "macos":
        return MacOSAdapter()
    raise PlatformNotSupportedError(f"Unsupported platform specified: {chosen}")
