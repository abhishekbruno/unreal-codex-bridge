# Unreal Codex Bridge — ARC 01.5 Stabilization & Security Report

**Document Version:** 1.0.0  
**Date:** 2026-11-20  
**Milestone:** ARC 01.5 Stabilization, Security Hardening & ARC 02 Foundation  
**Engine:** Unreal Engine 5.8.4 (CL 58902052)  
**Endpoint:** `http://127.0.0.1:8000/mcp`  
**Repository:** `https://github.com/abhishekbruno/unreal-codex-bridge`  

---

## 1. Executive Summary

ARC 01 established the core transport, handshake, and tool discovery mechanisms connecting OpenAI Codex to Unreal Engine 5.8 via the Model Context Protocol (MCP). However, the comprehensive functional audit identified two P0 blockers and one P1 architectural constraint:
1. **P0 Listener Security (BUG-01):** Missing `guard_listener_overrides` function in `scripts/configure.py`, causing `test_public_port_override_rejected_before_configuration` to fail and leaving the editor vulnerable to public network exposure.
2. **P0 Codex CLI Windows Resolution (BUG-02):** Unresolved `.cmd` extension on Windows in `scripts/doctor.py`, producing `FileNotFoundError [WinError 2]`.
3. **P1 Static Toolset Catalog (DES-01):** Hardcoded selection of only 6 toolsets at startup, preventing Codex from accessing the remaining 47 observed toolsets (such as `BlueprintTools`, `UMGToolSet`, `PhysicsAssetToolset`, etc.).

ARC 01.5 has systematically resolved all three issues, verified zero regressions across 45 automated unit tests, and validated live editor functionality against Unreal Engine 5.8.4.

---

## 2. P0 Security Fix: MCP Listener Security Hardening

### 2.1 Problem Description
The Unreal Engine MCP server binds to HTTP port 8000. Under default or misconfigured settings, an editor could inadvertently bind to wildcard (`0.0.0.0`, `::`) or public network interfaces, allowing arbitrary external network clients to issue remote tool calls into the live Unreal Engine editor session. The test `test_public_port_override_rejected_before_configuration` failed because `guard_listener_overrides` was unimplemented.

### 2.2 Architectural Implementation
In `scripts/configure.py`, robust validation and defensive guards were implemented:
1. **IP Address & Loopback Parsing (`is_valid_loopback_host`):**
   - Utilizes Python's `ipaddress` module to parse both IPv4 and IPv6 addresses.
   - Strictly permits loopback addresses: `127.0.0.1`, `::1`, and literal `localhost`.
   - Explicitly rejects wildcard addresses: `0.0.0.0`, `::`, `*`, `any`.
   - Rejects public, private non-loopback (e.g. `192.168.x.x`, `10.x.x.x`), link-local, and multicast addresses.
2. **Robust INI Configuration Parser (`parse_listener_override`):**
   - Parses `[HTTPServer.Listeners]` sections in `DefaultEngine.ini`.
   - Checks `DefaultBindAddress` directives.
   - Detects port-specific overrides in the format `(Port=8000, BindAddress="0.0.0.0")` or comma-separated tuples.
3. **Pre-flight Guard (`guard_listener_overrides`):**
   - Evaluates all engine INI configurations before any file modifications or backups are executed.
   - Raises explicit `ValueError` if an unsafe override is detected, stopping configuration changes immediately.
   - Preserves all unrelated INI sections and user comments.

### 2.3 Verification & Regression Tests
Added comprehensive test suite `test_listener_overrides_comprehensive_security` in `tests/test_configure.py`:
- Valid IPv4 loopback (`127.0.0.1`) -> PASS
- Valid IPv6 loopback (`::1`) -> PASS
- Wildcard binding (`0.0.0.0`, `::`, `*`) -> REJECTED (ValueError)
- Public IP binding (`203.0.113.195`) -> REJECTED (ValueError)
- Private non-loopback (`192.168.1.50`) -> REJECTED (ValueError)
- Conflicting port override binding to public IP -> REJECTED (ValueError)
- All 8 configuration tests passed in 0.136s.

---

## 3. P0 Windows Fix: Codex CLI Resolution

### 3.1 Problem Description
On Windows platforms, `codex` is distributed as a global npm script with executable wrappers `codex.cmd` and `codex.ps1`. Invoking `subprocess.check_output(['codex', '--version'])` without the `.cmd` extension triggers Win32 `CreateProcessW` failure `[WinError 2] The system cannot find the file specified`. Furthermore, running `.ps1` fails under default PowerShell `ExecutionPolicy` restrictions.

### 3.2 Architectural Implementation
In `scripts/doctor.py`:
1. Implemented `resolve_codex_bin()`:
   - On Windows (`os.name == 'nt'`), searches `shutil.which('codex.cmd')` first, followed by `shutil.which('codex.exe')`.
   - On POSIX platforms, searches `shutil.which('codex')`.
   - Avoids `shell=True` to eliminate shell injection vulnerabilities and security risks.
2. Differentiated Error Handling:
   - Catches `subprocess.CalledProcessError` (CLI executable failed or returned non-zero).
   - Catches `json.JSONDecodeError` / `UnicodeDecodeError` cleanly.
   - Formats clear, actionable status messages in `doctor.py`.

### 3.3 Live Verification
Running `scripts/doctor.py` against Unreal Engine 5.8:
- `PASS codex_cli codex-cli 0.171.0`
- `PASS codex_configuration {'path': '...', 'server': 'unreal-mcp', 'recognized_by_codex': True}`
- All 11 diagnostic checks in `doctor.py` reported PASS with 0 errors.

---

## 4. P1 Dynamic Toolset Discovery

### 4.1 Problem Description
The Unreal Engine 5.8 native MCP server exposes 53 distinct toolsets totaling 832 tools. `UnrealSession.connect()` previously preloaded only 6 selected toolsets (`SceneTools`, `ActorTools`, `AssetTools`, `ObjectTools`, `LogsToolset`, `EditorAppToolset`). Any attempt by Codex to call tools in other toolsets (e.g. `BlueprintTools`, `UMGToolSet`) resulted in `MCPError: Missing or ambiguous capability`.

### 4.2 Architectural Implementation
In `scripts/unreal_session.py`:
1. Added `UnrealSession.load_toolset(toolset_name)`:
   - Inspects `self.catalog` to check if the toolset is already cached.
   - If not cached, looks up `toolset_name` against `self.names` (all 53 discovered toolsets).
   - Issues a dynamic `describe_toolset` call to the live MCP server.
   - Validates the returned schema and appends the toolset definition to `self.catalog`.
2. Enhanced `UnrealSession.tool(toolset_name, tool_name)`:
   - Automatically invokes `load_toolset` on demand.
   - Matches tools by short name or fully qualified identifier.
   - Provides clear diagnostics listing available tools if a tool name is missing.

### 4.3 Live Verification
Tested with `BlueprintTools`:
- Initial catalog size: 6 toolsets.
- Calling `session.invoke('BlueprintTools', 'get_graph_dsl_docs')` dynamically loaded `BlueprintTools` into the catalog (catalog size: 7) and retrieved the complete Graph DSL grammar documentation.

---

## 5. Regression Test Results

| Test Module | Tests | Result | Duration |
|:---|:---:|:---:|:---:|
| `tests/test_configure.py` | 8 | PASS | 0.14s |
| `tests/test_diagnostics.py` | 9 | PASS | 0.06s |
| `tests/test_bridge.py` | 8 | PASS | 0.05s |
| `tests/test_transport.py` | 6 | PASS | 0.12s |
| `tests/test_install.py` | 4 | PASS | 3.50s |
| `tests/test_live_guards.py` | 3 | PASS | 0.02s |
| `tests/test_inspect_project.py` | 7 | PASS | 0.01s |
| **Total Test Suite** | **45** | **PASS (100%)** | **3.89s** |

---

## 6. Conclusion & Status

ARC 01.5 is **100% complete**. All identified P0 and P1 issues are resolved, security hardening is in place, and the platform foundation is ready for ARC 02 (Project Intelligence & Scene Graph Authoring).

