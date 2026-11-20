# Unreal Codex Bridge Architecture

The **Unreal Codex Bridge** integrates OpenAI Codex with Unreal Engine using Epic Games' native Model Context Protocol (MCP) server plugins. It provides diagnostic verification, process-level identity protection, safe live automation, and modular development skills for AI-assisted Unreal development.

---

## 1. High-Level Architecture

```
+-------------------------------------------------------------+
|                        Codex Client                         |
|   (Codex CLI / ChatGPT Desktop / Automated Bridge Client)   |
+------------------------------+------------------------------+
                               |
                   HTTP POST / SSE Transport
               (Loopback: http://127.0.0.1:8000/mcp)
                               |
                               v
+-------------------------------------------------------------+
|                    Unreal Engine Editor                     |
|                                                             |
|  +-------------------------------------------------------+  |
|  |           ModelContextProtocol Native Plugin          |  |
|  |  - Embedded HTTP Server (HTTPServer listener)         |  |
|  |  - JSON-RPC 2.0 Request Router                        |  |
|  |  - SSE Event Stream Producer                          |  |
|  +---------------------------+---------------------------+  |
|                              |                              |
|                              v                              |
|  +-------------------------------------------------------+  |
|  |              Toolset Registry Subsystem               |  |
|  |  - Tool discovery: list_toolsets, describe_toolset   |  |
|  |  - Dispatcher: call_tool                              |  |
|  +---------------------------+---------------------------+  |
|                              |                              |
|         +--------------------+--------------------+         |
|         v                    v                    v         |
|  +--------------+     +--------------+     +--------------+ |
|  |  SceneTools  |     |  ActorTools  |     |  AssetTools  | |
|  +--------------+     +--------------+     +--------------+ |
|         v                    v                    v         |
|  +--------------+     +--------------+     +--------------+ |
|  | ObjectTools  |     | LogsToolset  |     |EditorAppTools| |
|  +--------------+     +--------------+     +--------------+ |
+-------------------------------------------------------------+
```

---

## 2. Core Components

### A. Transport Layer (`scripts/bridge_mcp.py`)
- Implements a lightweight, sequential client for MCP over **Streamable HTTP** with **Server-Sent Events (SSE)**.
- Adheres strictly to JSON-RPC 2.0 specifications.
- Restricts connections to RFC-defined loopback addresses (`127.0.0.1` / `localhost`) to prevent cross-machine exposure.
- Enforces redirect rejection to prevent DNS rebinding or SSRF attacks.
- Tracks protocol version negotiation (`2025-11-25`, `2025-06-18`, etc.) and session identifiers (`Mcp-Session-Id`).

### B. Session and Dynamic Toolset Discovery (`scripts/unreal_session.py`)
- Queries top-level tools (`list_toolsets`, `describe_toolset`, `call_tool`).
- Validates that the engine exposes the required tool-search interface (`bEnableToolSearch`).
- Inspects input schemas dynamically against argument dictionaries prior to transmission.
- Distinguishes verified read operations from conservative write operations.

### C. Active Project & Process Identity Verification
Before executing scene mutations, the bridge performs two-factor verification to ensure it is targeting the correct editor instance:
1. **OS Listener Inspection**: Uses PowerShell CIM / Win32_Process to verify that the listener on the target TCP port is an authentic `UnrealEditor.exe` binary belonging to the specified Unreal Engine installation, and that its command line points uniquely to the expected `.uproject` file.
2. **In-Session Log Inspection**: Calls `LogsToolset.GetLogEntries` via MCP to inspect `LogInit` startup records verifying that the running game matches the project name and that the engine version is UE 5.8.

### D. Configuration Management (`scripts/configure.py`)
- Idempotently updates project `.uproject` files to enable `ModelContextProtocol` and `AllToolsets`.
- Configures `Config/DefaultEditorPerProjectUserSettings.ini` for automatic server launch and port binding.
- Sets `Config/DefaultEngine.ini` to enforce `127.0.0.1` loopback binding.
- Updates `.codex/config.toml` to register the MCP server without clobbering existing configuration.
- Generates timestamped backups for every modified file (`*.backup-<timestamp>`).

### E. Diagnostic & Live Verification (`scripts/doctor.py`, `scripts/live_test.py`)
- `doctor.py` provides an offline-to-online diagnostic runner reporting PASS, FAIL, BLOCKED, or NOT TESTED statuses across Python, Codex CLI, Unreal installation, project plugins, configuration, TCP loopback, MCP handshake, and project identity.
- `live_test.py` performs automated integration testing: duplicates a template level into a uniquely named test map (`ARC01_TestLevel`), spawns a static mesh actor (`Codex_Test_Cube`), asserts world transform and reflection properties, persists the map, and reloads it to confirm serialization.

---

## 3. Security Boundary

- **Unauthenticated Local Server**: Epic's built-in `ModelContextProtocol` plugin operates without authentication tokens. It must remain strictly confined to the loopback interface (`127.0.0.1`).
- **No Direct Remote Access**: Web-based or cloud-hosted AI agents cannot and should not connect directly to the editor's port. Any remote access requires an authenticated, hardened gateway proxy.
- **Project Isolation**: All destructive operations (deletions, overwrites) require explicit confirmation. The live test suite never modifies existing user maps or assets.
