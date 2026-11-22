"""Validation of native macOS platform adapter on authentic Darwin runners."""
import os
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "scripts"))

from platform_adapter.macos import MacOSAdapter


def validate():
    adapter = MacOSAdapter()
    os_info = adapter.detect_os()
    print(f"Native macOS Detection: {os_info}")
    sys_name = os_info.get("system")
    arch = adapter.detect_architecture()
    assert sys_name == "Darwin", f"Expected Darwin, got {sys_name}"
    assert arch in ("arm64", "x86_64"), f"Unexpected architecture: {arch}"

    # Test native OS-level executable resolution via libproc proc_pidpath on own PID
    my_pid = os.getpid()
    exe = adapter.get_process_executable(my_pid)
    print(f"Native PID {my_pid} executable: {exe}")
    assert exe is not None and exe.is_file(), f"Failed resolving executable for PID {my_pid}"
    print("Native macOS libproc proc_pidpath verification PASSED.")
    return True


if __name__ == "__main__":
    validate()
