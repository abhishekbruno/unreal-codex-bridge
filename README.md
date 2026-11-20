# Unreal Codex Bridge

> **Status: Experimental**  
> This project is an early-stage, experimental bridge connecting OpenAI Codex to Unreal Engine via Epic Games' native Model Context Protocol (MCP) server. Functionality is actively evolving and should only be evaluated in development environments.

---

## 1. Project Overview

The **Unreal Codex Bridge** enables OpenAI Codex (via the Codex CLI or OpenAI desktop integrations) and external AI agents to inspect, query, and programmatically drive a running Unreal Engine Editor.

By building on top of Epic Games' native `ModelContextProtocol` and `AllToolsets` engine plugins, the bridge avoids custom binary injectors or engine patches. Instead, it provides a lightweight, loopback-bound client, session verification guards, safety preflights, configuration management, and developer skills to orchestrate Unreal Editor workflows safely.

---

## 2. Unreal Engine Compatibility Target

- **Primary Compatibility Target:** **Unreal Engine 5.8** (Verified against **UE 5.8.4 CL 58902052** on Windows 11/10).
- **Required Native Plugins:**
  - `ModelContextProtocol` (`Engine/Plugins/Experimental/ModelContextProtocol/ModelContextProtocol.uplugin`)
  - `AllToolsets` (`Engine/Plugins/Experimental/Toolsets/AllToolsets/AllToolsets.uplugin`)
  - `ToolsetRegistry` (`Engine/Plugins/Experimental/ToolsetRegistry/ToolsetRegistry.uplugin`)
- **Python Runtime:** Python 3.10+ (Standard library only; tested on Python 3.12).
- **Secondary / Future Path (UE 5.9+):** Unreal Engine 5.9 introduces an in-editor **Unreal Assistant** panel supporting the Agent Client Protocol (ACP) adapter (`@agentclientprotocol/codex-acp`). While this package includes skills compatible with that flow, the core tools and ARC 01 verification target the external Streamable HTTP/SSE MCP connection available in UE 5.8.

---

## 3. Codex MCP Integration Architecture

The bridge architecture operates across three main tiers:

```
+-------------------------------------------------------------+
|                        Codex Client                         |
|             (Codex CLI / ChatGPT Desktop Agent)             |
+------------------------------+------------------------------+
                               |
                 Loopback Streamable HTTP / SSE
                   (http://127.0.0.1:8000/mcp)
                               |
                               v
+-------------------------------------------------------------+
|                    Unreal Engine Editor                     |
|                                                             |
|  +-------------------------------------------------------+  |
|  |           ModelContextProtocol Native Plugin          |  |
|  |  - Embedded HTTP Server (HTTPServer listener)         |  |
|  |  - JSON-RPC 2.0 Router & SSE Response Streamer        |  |
|  +---------------------------+---------------------------+  |
|                              |                              |
|                              v                              |
|  +-------------------------------------------------------+  |
|  |              Toolset Registry Subsystem               |  |
|  |  - Dynamic tool discovery (list_toolsets, describe)   |  |
|  |  - Safe dispatching via call_tool                     |  |
|  +-------------------------------------------------------+  |
+-------------------------------------------------------------+
```

### Key Architectural Safeguards
1. **Loopback-Only Transport (`scripts/bridge_mcp.py`):** The MCP client communicates exclusively via loopback IP addresses (`127.0.0.1` / `localhost`). Redirects to remote endpoints are explicitly refused.
2. **Two-Factor Project Identity Verification (`scripts/unreal_session.py`):**
   - **Process Identity:** Uses Windows CIM / PowerShell process inspection to verify that the listener on the target TCP port is an authentic `UnrealEditor.exe` from the designated engine installation, and that its command line points to the expected `.uproject`.
   - **Log Telemetry:** Queries `LogsToolset.GetLogEntries` through MCP to ensure the active editor session is running the correct project and engine version before any scene mutation is authorized.
3. **Safe Execution Guards (`scripts/live_test.py`):** Creation workflows duplicate clean template maps (`/Engine/Maps/Templates/Template_Default`) into unique, non-colliding test maps (`/Game/CodexBridgeTests/ARC01_TestLevel...`). Existing assets and levels are never overwritten or modified.

For full technical details, see [`docs/architecture.md`](docs/architecture.md) and [`docs/SECURITY.md`](docs/SECURITY.md).

---

## 4. Available Functionality

### Core Scripts (`scripts/`)
| Script | Description | Status |
| :--- | :--- | :--- |
| `bridge_mcp.py` | Streamable HTTP and SSE MCP client with JSON-RPC 2.0 handling, session headers, and loopback enforcement. | **Implemented & Verified** |
| `doctor.py` | Diagnostics runner performing system, CLI, engine, plugin, loopback, MCP handshake, and identity checks. | **Implemented & Verified** |
| `unreal_session.py` | Toolset catalog discovery, input schema validation, and process identity verification. | **Implemented & Verified** |
| `configure.py` | Backed-up configuration utility for `.uproject`, editor INI settings, and `.codex/config.toml`. | **Implemented (1 pending test)** |
| `live_test.py` | End-to-end live testing script for verifying level duplication, actor spawning, transform setting, and persistence. | **Implemented & Verified** |
| `install.py` | Portable installer for registering skills and MCP configuration into an Unreal project. | **Implemented & Verified** |

### Codex Skills (`skills/`)
| Skill | Description | Status |
| :--- | :--- | :--- |
| `unreal-mcp` | Workflows and operational guidelines for querying and modifying running Unreal projects via MCP. | **Implemented** |
| `create-toolset` | Architectural and C++ guidance for extending Unreal MCP with custom native toolsets. | **Implemented** |
| `unreal-skill` | General Unreal Engine development patterns, asset conventions, and system rules. | **Implemented** |

### Offline Test Suites (`tests/`)
| Test Module | Coverage | Status |
| :--- | :--- | :--- |
| `test_bridge.py` | 8 tests: Protocol handling, response unpacking, loopback validation, error mapping. | **Passing (8/8)** |
| `test_diagnostics.py` | 6 tests: Engine checks, version validation, process identity rejection, schema validation. | **Passing (6/6)** |
| `test_live_guards.py` | 3 tests: Non-colliding map name selection, transform assertions. | **Passing (3/3)** |
| `test_transport.py` | 6 tests: HTTP/SSE transport, redirect refusal, session headers, pagination. | **Passing (6/6)** |
| `test_install.py` | 4 tests: Plugin enablement, backup generation, INI and marketplace merging. | **Passing (4/4)** |
| `test_configure.py` | 6 tests: Plugin preservation, TOML idempotence, backup creation, override checks. | **5 Passing / 1 Error** *(See ARC 01 Status)* |

---

## 5. Installation and Configuration

### Prerequisites
1. **Windows 10 / 11** with PowerShell 5.1+.
2. **Unreal Engine 5.8** installed (with Editor symbols / tools).
3. **Python 3.10+** (Python 3.12 recommended).
4. **OpenAI Codex CLI** installed and authenticated (`codex login`).

### Step 1: Configure Your Unreal Engine Project
Your `.uproject` file must enable the native MCP plugins:
```json
{
  "FileVersion": 3,
  "Plugins": [
    { "Name": "ModelContextProtocol", "Enabled": true },
    { "Name": "AllToolsets", "Enabled": true }
  ]
}
```

### Step 2: Configure Loopback Security and Auto-Start
Add the following to your project's configuration INI files (or copy from `templates/`):

**`Config/DefaultEngine.ini`**:
```ini
[HTTPServer.Listeners]
DefaultBindAddress=127.0.0.1
```

**`Config/DefaultEditorPerProjectUserSettings.ini`**:
```ini
[/Script/ModelContextProtocolEngine.ModelContextProtocolSettings]
bAutoStartServer=True
ServerPortNumber=8000
ServerUrlPath=/mcp
```

Alternatively, use `scripts/configure.py` to preview or apply changes with automated backups:
```powershell
python scripts/configure.py --project "D:\Path\To\MyProject.uproject" --engine "D:\UE_5.8" --apply
```

### Step 3: Register the MCP Server with Codex
Create or merge `.codex/config.toml` in your project root:
```toml
[mcp_servers.unreal-mcp]
url = "http://127.0.0.1:8000/mcp"
```

### Step 4: Run Preflight Diagnostics
Launch your Unreal Editor project, then run the diagnostic suite:
```powershell
python scripts/doctor.py --project "D:\Path\To\MyProject.uproject" --engine "D:\UE_5.8"
```
Ensure all required checks return `PASS`.

---

## 6. ARC 01 Development Status

The primary milestone of ARC 01 was to verify a complete programmatic actor creation cycle through Epic's native UE 5.8 MCP server without third-party plugins or engine modifications.

### Verified Live Capabilities:
- **Editor Handshake:** Successful JSON-RPC 2.0 handshake over Streamable HTTP/SSE with protocol version negotiation (`2025-11-25`).
- **Dynamic Toolset Discovery:** Discovered and queried native toolsets: `SceneTools`, `ActorTools`, `AssetTools`, `ObjectTools`, `LogsToolset`, and `EditorAppToolset`.
- **Level Duplication:** Successfully duplicated `/Engine/Maps/Templates/Template_Default` into `/Game/CodexBridgeTests/ARC01_TestLevel`.
- **Actor Creation:** Spawned `Codex_Test_Cube` from asset `/Engine/BasicShapes/Cube` at location `(0, 0, 150)`.
- **Property Reflection Verification:** Verified actor transform and component static mesh property assignment using `ObjectTools.get_properties`.
- **Map Persistence & Reload:** Persisted the level to disk (`.umap`), reloaded the original level, and reloaded the test level to confirm asset serialization.

### Current Test Suite Status:
- **Total Tests:** 33 unit tests across 6 modules.
- **Passing:** 32 tests.
- **Pending Remediation:** 1 test in `tests/test_configure.py`:
  - `test_public_port_override_rejected_before_configuration` fails with `AttributeError: module 'configure' has no attribute 'guard_listener_overrides'`. This validation helper is documented and scheduled for resolution in the next development cycle.

---

## 7. Known Limitations

- **Experimental Protocol:** The Unreal MCP plugin in UE 5.8 is experimental. Tool names, input schemas, and return formats may vary between Unreal Engine releases.
- **Unauthenticated Local Server:** Epic's native HTTP server does not support token-based authentication. It must never be exposed to public networks or untrusted local networks.
- **Single Active Editor Instance:** The default MCP listener binds to port 8000. Running multiple editor instances concurrently requires per-project port offset configuration.
- **Game Thread Serialization:** Complex editor operations execute synchronously on the Unreal Editor main game thread; long-running operations can cause temporary client-side timeouts if not batched appropriately.

---

## 8. Planned Development Roadmap

- [ ] **Config Hardening:** Implement `guard_listener_overrides` in `scripts/configure.py` to complete 100% test suite pass rate.
- [ ] **Multi-Instance Port Routing:** Automatically discover active Unreal Editor ports and resolve multi-instance collisions.
- [ ] **Extended Toolset Coverage:** Add high-level abstractions for Blueprint node graph authoring, UMG widget composition, and Niagara emitter parameters.
- [ ] **CI Test Automation:** Configure GitHub Actions for offline mock unit testing across Python 3.10, 3.11, and 3.12.
- [ ] **Unreal Engine 5.9 ACP Bridge:** Provide native in-editor ACP guidance and adapters for the UE 5.9 Unreal Assistant workflow.

---

## 9. Credits and Licensing

- **Original Epic Games Skills:** Portions of the included developer skills are adapted from Epic Games' MIT-licensed `unreal-engine-skills-for-claude-code-plugin` repository.
- **License:** Released under the [MIT License](LICENSE). Copyright (c) 2026 Epic Games, Inc. and contributors.
- **Disclaimer:** This project is an independent community development and is not officially affiliated with Epic Games or OpenAI.
