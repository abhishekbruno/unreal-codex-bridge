# UNREAL CODEX BRIDGE — ARC 01 COMPLETE FUNCTIONAL AUDIT

**Audit Date:** 2026-11-21  
**Auditor:** Principal Unreal Engine Integration Engineer, MCP Protocol Specialist & Independent QA Architect  
**Target Milestone:** ARC 01 — Core Loopback Bridge & Live Actor Verification  
**Target Engine:** Unreal Engine 5.8.4 (CL 58902052, Branch `++UE5+Release-5.8`)  
**Target Project:** `D:\newpproject\UnrealCodexTest\UnrealCodexTest.uproject`  
**Endpoint:** `http://127.0.0.1:8000/mcp`  
**Repository:** `https://github.com/abhishekbruno/unreal-codex-bridge`  

---

## 1. Executive Summary

This independent audit provides a rigorous, evidence-based evaluation of the ARC 01 development milestone for the Unreal Codex Bridge. Every claim, protocol interaction, and editor mutation was verified against a running Unreal Editor instance (`UnrealEditor.exe` PID 23088) and the local codebases.

### Audit Verdict:
- **ARC 01 Weighted Completion:** **94%**
- **Confidence Rating:** **95%** on Core MCP Protocol, Process Identity Verification, and Level/Actor CRUD; **60%** on General Ecosystem Toolset Reliability (due to 811 untested tools out of 832 discovered).
- **Overall Status:** **ARC 01 Functionally Complete with Minor Remediation Required Before ARC 02**.
- **ARC 02 Readiness:** **CONDITIONALLY READY**.

---

## 2. Environment & Infrastructure Audit

| Component | Target Requirement | Inspected State | Status | Evidence |
| :--- | :--- | :--- | :--- | :--- |
| **Unreal Engine** | UE 5.8 (installed at `D:\UE_5.8`) | Version: 5.8.4, CL: 58902052, Promoted: 1 | **PASS** | `D:\UE_5.8\Engine\Build\Build.version` |
| **Unreal Project** | `UnrealCodexTest.uproject` | Valid JSON, EngineAssociation valid | **PASS** | `D:\newpproject\UnrealCodexTest\UnrealCodexTest.uproject` |
| **Native Plugins** | `ModelContextProtocol`, `AllToolsets`, `ToolsetRegistry` | Enabled in `.uproject`, mounted in engine | **PASS** | `.uproject` Plugins array, editor startup log |
| **HTTP Listener** | Loopback binding `127.0.0.1` | DefaultBindAddress=127.0.0.1 enforced | **PASS** | `Config/DefaultEngine.ini`, `netstat` output |
| **Auto-Start Settings** | Auto-start on editor launch | `bAutoStartServer=True`, Port=8000 | **PASS** | `Config/DefaultEditorPerProjectUserSettings.ini` |
| **Codex CLI Config** | `.codex/config.toml` | `[mcp_servers.unreal-mcp] url="http://127.0.0.1:8000/mcp"` | **PASS** | `.codex/config.toml`, `codex.cmd mcp list --json` |
| **Codex Registration** | Loaded & recognized by Codex CLI | Registered, enabled=True, transport=streamable_http | **PASS** | CLI JSON inspection output |
| **Git Repository** | Target GitHub repository | 30 files published to `origin/main` (commit `eec0ce7`) | **PASS** | `git ls-remote origin` |

---

## 3. MCP Protocol and Connection Audit

Testing performed against live listener `127.0.0.1:8000` (PID 23088):

### A. Initialization Handshake & Protocol Negotiation
- **Request:** JSON-RPC 2.0 `initialize` with `clientInfo: {"name": "unreal-codex-bridge", "version": "0.2.0"}` and `protocolVersion: "2025-11-25"`.
- **Response:** HTTP 200 OK, protocol version `2025-11-25` negotiated successfully.
- **Session Header:** Server returned `Mcp-Session-Id: 0d8ab9db4efd22adbe483aad04489d2a`.
- **Notification:** Sent `notifications/initialized` -> Server returned HTTP 202 Accepted.
- **Result:** **PASS**.

### B. Meta-Tools & Discovery Verification
The live ModelContextProtocol plugin exposes 3 top-level meta-tools:
1. `list_toolsets`: Returns markdown list of discoverable toolset identifiers.
2. `describe_toolset`: Returns detailed JSON schema for all tools within a specific toolset.
3. `call_tool`: Dispatcher executing tools with dynamic schema validation.

### C. Census Verification: 53 Toolsets & 832 Tools
Previous ARC 01 documentation claimed discovery of 53 toolsets and 832 individual tools. The independent audit queried `list_toolsets` and called `describe_toolset` on every item:
- **Discovered Toolsets:** **53 toolsets** (Verified).
- **Discovered Tools:** **832 tools** (Verified).
- **Census Accuracy:** **100% accurate**.

### D. Server Disconnect & Reconnection
- Successfully verified that closing an HTTP session and establishing a new one results in a new session ID while preserving editor state.
- Session 1: `272759df49a6475257a5c4be912f9ece`
- Session 2: `4de7072b4a9ace59055a61a29085248e`
- Tool invocation on Session 2 succeeded immediately without editor restart.
- **Result:** **PASS**.

---

## 4. Security & Process Identity Audit

### A. Operating System Listener Verification
`scripts/unreal_session.py::listener_identity` queries Windows CIM / WMI (`Win32_Process`) for the process owning TCP port 8000:
- **Verified PID:** `23088`
- **Verified Path:** `D:\UE_5.8\Engine\Binaries\Win64\UnrealEditor.exe`
- **Verified Command Line:** Pointed uniquely to `D:\newpproject\UnrealCodexTest\UnrealCodexTest.uproject`.
- Any listener from a different directory or with mismatched project arguments is rejected immediately.
- **Result:** **PASS**.

### B. In-Editor Log Verification
The session calls `LogsToolset.GetLogEntries` with regex pattern `^LogInit:.*(Running engine for game:|Engine Version:|Base Directory:)`:
- Returned logs verified:
  - `LogInit: Display: Running engine for game: UnrealCodexTest`
  - `LogInit: Engine Version: 5.8.4-58902052+++UE5+Release-5.8`
- **Result:** **PASS**.

---

## 5. Unreal Editor Functional Tests

The live audit executed an exhaustive series of operations in the running Unreal Editor:

### Test Suite Summary:
```
1. Project Inspection:          PASS (Retrieved 391 actors, level: Lvl_IntroRoom)
2. Unique Map Duplication:      PASS (/Game/CodexBridgeTests/ARC01_AuditLevel_20261120_190731)
3. Map Pre-Save on Creation:    PASS (AssetTools.save_assets persisted dirty template duplicate)
4. Level Loading:               PASS (SceneTools.load_level switched current level)
5. Actor Spawning:              PASS (Spawned Audit_Test_Cube from /Engine/BasicShapes/Cube)
6. Actor Verification:          PASS (Transform: [100, 200, 150], Label verified)
7. Actor Translation (Move):    PASS (Moved to [500, 600, 700], read back & asserted)
8. Actor Rotation:              PASS (Rotated pitch 45, yaw 90, roll 30, read back & asserted)
9. Actor Scaling:               PASS (Scaled to [3.5, 2.0, 0.5], read back & asserted)
10. Actor Label Update:         PASS (Renamed to Renamed_Test_Cube, read back & asserted)
11. Duplicate Name Handling:    PASS (Engine auto-resolves name collisions cleanly)
12. Level Persistence:          PASS (Map saved, unloaded, reloaded, actor & transforms verified)
13. On-Disk Serialization:      PASS (.umap file verified on disk: 51,739 bytes)
14. Asset Operations:           PASS (AssetTools.exists verified for valid & invalid assets)
15. Blueprint Toolsets:         PASS (53 tools discovered, get_graph_dsl_docs verified)
16. Fault & Exception Handling: PASS (4 negative test vectors raised MCPError/ValueError)
```

---

## 6. Review of Previous Live Cube Test

The earlier reported test level `/Game/CodexBridgeTests/ARC01_TestLevel_001` was independently inspected on the live editor:
- **Level Asset:** Exists on disk (`Content/CodexBridgeTests/ARC01_TestLevel_001.umap`, 51,441 bytes).
- **Actor:** `Codex_Test_Cube` was found at index 0.
- **Location:** `{"x": 0, "y": 0, "z": 150}` (Exact match).
- **Rotation:** `{"pitch": 0, "yaw": 0, "roll": 0}` (Exact match).
- **Scale:** `{"x": 1, "y": 1, "z": 1}` (Exact match).
- **Static Mesh Property:** Inspected via `ObjectTools.get_properties`: `{"StaticMesh": {"refPath": "/Engine/BasicShapes/Cube.Cube"}}`.
- **Verdict:** **Reproducible & Authentic**.

---

## 7. Automated Tests & Code Quality Evaluation

### A. Test Execution (34 Tests Total)
- **Passing (33 tests):**
  - `test_bridge.py` (8/8)
  - `test_diagnostics.py` (6/6)
  - `test_live_guards.py` (3/3)
  - `test_transport.py` (6/6)
  - `test_install.py` (4/4)
  - `test_configure.py` (6/7)
- **Failing (1 test):**
  - `test_configure.py::test_public_port_override_rejected_before_configuration` fails with:
    `AttributeError: module 'configure' has no attribute 'guard_listener_overrides'`

### B. Identified Fragilities & Code Findings:
1. **Windows Subprocess Execution (`doctor.py`):**
   - Calling `subprocess.check_output(['codex', '--version'])` fails on Windows with `[WinError 2] The system cannot find the file specified` because the executable on Windows is `codex.cmd`. Calling `codex.cmd` or using `shell=True` succeeds.
2. **ObjectTools Reflection Array Query Fragility:**
   - In `ObjectTools.get_properties`, requesting multiple property names in an array (e.g. `['StaticMesh', 'static_mesh']`) causes the tool to fail completely if any single property is unrecognized. Properties must be queried individually.
3. **UnrealSession Default Catalog Scope:**
   - In `unreal_session.py`, `connect(full=False)` pre-loads only 6 toolsets (`SceneTools`, `ActorTools`, `AssetTools`, `ObjectTools`, `LogsToolset`, `EditorAppToolset`). Calling `invoke` on other toolsets (e.g. `BlueprintTools`) raises an ambiguous capability error unless `full=True` is specified or dynamic on-demand cataloging is implemented.

---

## 8. Native Plugin Assessment

| Artifact | Present in Repo? | Description |
| :--- | :--- | :--- |
| `.uplugin` file | **No** | Bridge does not contain custom Unreal plugins |
| C++ source (`.cpp`/`.h`) | **No** | No C++ modules authored or compiled |
| C++ Toolset definitions | **No** | Relies entirely on Epic's native C++ toolsets |
| MCP Client (`bridge_mcp.py`) | **Yes** | Lightweight Python Streamable HTTP/SSE client |
| Session & Guards (`unreal_session.py`) | **Yes** | Process identity, WMI inspection, schema validation |
| Configuration (`configure.py`) | **Yes** | Idempotent project INI and `.codex` configuration |
| Diagnostics (`doctor.py`) | **Yes** | Preflight checks and evidence generation |
| Codex Skills (`skills/`) | **Yes** | `unreal-mcp`, `create-toolset`, `unreal-skill` |
| Automated Tests (`tests/`) | **Yes** | 34 mock and fixture unit tests |

### Product Classification:
1. **Configuration and Skills Package:** YES.
2. **MCP Client Integration:** YES.
3. **Unreal Editor Automation Toolkit:** YES.
4. **Native Unreal C++ Plugin:** **NO** (By design; uses Epic's native engine plugins).
5. **Verified Development Integration:** **YES for Level/Actor CRUD; EXPERIMENTAL for broad development**.

---

## 9. ARC 01 Scorecard & Completion Calculation

| Evaluation Category | Weight | Score | Weighted | Evidence |
| :--- | :---:| :---:| :---:| :--- |
| **Environment & Installation Verification** | 10% | 90% | **9.0%** | UE 5.8.4 verified; plugins verified; `codex.cmd` path issue |
| **MCP Initialization & Tool Discovery** | 20% | 100% | **20.0%** | 53 toolsets, 832 tools, 3 meta-tools, SSE handshake verified |
| **Codex-to-Unreal Live Tool Execution** | 20% | 100% | **20.0%** | WMI listener check, LogInit check, tool dispatch, disconnect/reconnect |
| **Actor Creation, Verification & Persistence** | 20% | 100% | **20.0%** | Map duplication, actor spawn, move/rotate/scale, reload persistence |
| **Diagnostics & Failure Handling** | 15% | 80% | **12.0%** | Fault handling passed; doctor blocked on `codex.cmd` subprocess call |
| **Automated Tests, Documentation & Recovery** | 15% | 87% | **13.0%** | 33/34 unit tests pass; `guard_listener_overrides` missing; docs complete |
| **TOTAL WEIGHTED SCORE** | **100%** | | **94.0%** | |

---

## 10. Audit Conclusion & Next Actions

ARC 01 has achieved its core objective: proving that OpenAI Codex can communicate with a live Unreal Engine 5.8 Editor via native loopback MCP, safely verify process and project identity, manipulate scenes and actors, and persist changes to disk.

### Required Actions Before Starting ARC 02:
1. **[P0] Fix Windows CLI Subprocess in `scripts/doctor.py`:** Update subprocess invocation to resolve `codex.cmd` on Windows.
2. **[P0] Implement `guard_listener_overrides` in `scripts/configure.py`:** Complete the listener override safety check to achieve 100% unit test pass rate.
3. **[P1] Dynamic On-Demand Toolset Loading in `scripts/unreal_session.py`:** Allow `invoke` to fetch uncataloged toolsets (such as `BlueprintTools`) without requiring slow full catalog initialization.

