"""Platform abstraction package for Unreal Codex Bridge."""

from .base import PlatformAdapter
from .windows import WindowsAdapter
from .macos import MacOSAdapter
from .detect import detect_system, get_platform_adapter, PlatformNotSupportedError

__all__ = [
    "PlatformAdapter",
    "WindowsAdapter",
    "MacOSAdapter",
    "detect_system",
    "get_platform_adapter",
    "PlatformNotSupportedError"
]
