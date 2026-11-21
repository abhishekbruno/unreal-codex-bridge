# Cross-Platform Architecture Specification
## Integration Sprint 01 — Unreal Codex Bridge

**Document Version:** 1.0.0  
**Target Environments:** Windows 10/11 & macOS (Apple Silicon arm64 & Intel x86_64)  
**Target Engine:** Unreal Engine 5.8.4 (Windows) / Unreal Engine 5.8.x (macOS)  

---

## 1. Architectural Philosophy: One Shared Product

The Unreal Codex Bridge is engineered as a **single, unified cross-platform product**. Developers on Windows and macOS clone the exact same repository, use the same CLI commands, and consume the same Codex skills without platform-conditional forks or duplicate repositories.

```
+--------------------------------------------------------------------------+
|                     OpenAI Codex / Codex CLI Agent                       |
+------------------------------------+-------------------------------------+
                                     |
                                     v
+--------------------------------------------------------------------------+
|                     unreal-codex-bridge (Codex Plugin)                    |
|  - .codex-plugin/plugin.json (Portable Plugin Manifest)                  |
|  - .agents/plugins/marketplace.json (Marketplace Catalog Definition)     |
|  - .mcp.json (Loopback HTTP Server Binding)                              |
|  - Skills: unreal-mcp, create-toolset, unreal-skill,                     |
|            unreal-game, unreal-playtest                                  |
+------------------------------------+-------------------------------------+
                                     |
                                     v
+--------------------------------------------------------------------------+
|                    Unified Editor Lifecycle Manager                      |
|                      `scripts/editor_lifecycle.py`                       |
|   Commands: detect, prepare, launch, connect, doctor, status, uninstall   |
+------------------------------------+-------------------------------------+
                                     |
            +------------------------+------------------------+
            |                                                 |
            v                                                 v
+-----------------------+                         +-----------------------+
|    Windows Adapter    |                         |     macOS Adapter     |
| `platform_adapter/    |                         | `platform_adapter/    |
|       windows.py`     |                         |        macos.py`      |
|                       |                         |                       |
| - Registry & Launcher |                         | - /Users/Shared/Epic  |
| - UnrealEditor.exe    |                         | - UnrealEditor.app    |
| - CIM / WMI Process   |                         | - lsof & ps utilities |
| - Netstat TCP owners  |                         | - arm64 / x86_64 arch |
| - codex.cmd / exe     |                         | - unix codex binary   |
| - PowerShell guards   |                         | - Posix log matching  |
+-----------------------+                         +-----------------------+
            |                                                 |
            +------------------------+------------------------+
                                     |
                                     v
+--------------------------------------------------------------------------+
|                   Shared Transport & Intelligence Layer                  |
|                                                                          |
|  - scripts/bridge_mcp.py: JSON-RPC 2.0 / Streamable HTTP & SSE           |
|  - scripts/unreal_session.py: Dynamic Toolset Catalog Discovery          |
|  - scripts/project_index.py: Persistent SQLite + FTS5 Caching            |
|  - scripts/project_dependencies.py: Reference DAG & Blast Radius         |
|  - scripts/blueprint_parser.py: S-Expression AST Visitor & Metrics       |
|  - scripts/playtest.py: PIE Execution & Runtime Telemetry Harvester      |
+------------------------------------+-------------------------------------+
                                     | Loopback HTTP/SSE (127.0.0.1:8000/mcp)
                                     v
+--------------------------------------------------------------------------+
|                         Unreal Engine Editor                             |
|                                                                          |
|  +--------------------------------------------------------------------+  |
|  |                 ModelContextProtocol Native Plugin                 |  |
|  |  - Embedded HTTP Server (HTTPServer listener bound to 127.0.0.1)   |  |
|  |  - JSON-RPC 2.0 Request Router & Streaming SSE Streamer            |  |
|  +---------------------------------+----------------------------------+  |
|                                    |                                     |
|                                    v                                     |
|  +--------------------------------------------------------------------+  |
|  |                    Toolset Registry Subsystem                      |  |
|  |  - Dynamic tool discovery (list_toolsets, describe_toolset)        |  |
|  |  - 53 Toolsets / 832 Tools (ActorTools, BlueprintTools, etc.)       |  |
|  +--------------------------------------------------------------------+  |
+--------------------------------------------------------------------------+
```

---

## 2. Core Abstractions & Decoupling

### 2.1 The Platform Adapter Pattern (`scripts/platform_adapter/`)
The `PlatformAdapter` abstract base class decouples operating-system-specific process and filesystem mechanics from the core protocol:

- **Operating System & Architecture Detection:**
  `detect_os()`, `detect_architecture()` reliably differentiate between Windows (`x86_64`, `arm64`) and macOS (`arm64` Apple Silicon vs `x86_64` Intel).
- **Engine Discovery:**
  - On Windows: Queries Epic Games Launcher JSON manifests under `%PROGRAMDATA%\Epic\EpicGamesLauncher\Data\Manifests\*.item`, common drive paths (`C:`, `D:`, `E:`), and `.uproject` relative `EngineAssociation`.
  - On macOS: Scans `/Users/Shared/Epic Games/UE_*`, user directories (`~/unreal`), and parses relative `EngineAssociation` descriptors.
- **Executable Resolution:**
  - Windows: `Engine/Binaries/Win64/UnrealEditor.exe`
  - macOS: `Engine/Binaries/Mac/UnrealEditor.app/Contents/MacOS/UnrealEditor`
- **Codex CLI Resolution:**
  - Windows: Checks for `codex.cmd`, `codex.exe`, and `%APPDATA%\npm\codex.cmd`.
  - macOS: Checks PATH for unix executable `codex`, `/opt/homebrew/bin/codex`, `/usr/local/bin/codex`; explicitly refuses `.cmd` shims.
- **Process Identity & Listener Ownership:**
  - Windows: Uses Windows CIM / PowerShell process queries and `netstat -ano` to confirm that the listening process on port 8000 is an authentic `UnrealEditor.exe` executing the designated `.uproject`.
  - macOS: Executes `/usr/sbin/lsof -nP -iTCP:<port> -sTCP:LISTEN -Fp` to isolate listening PID, queries `ps -p <pid> -o command=` to verify arguments, and validates open file handles against `Saved/Logs/<Game>.log`.

### 2.2 Shared Transport & Intelligence (Zero OS-Dependencies)
- **`bridge_mcp.py`:** Pure standard library HTTP/SSE client. Zero third-party dependencies (`urllib.request`, `http.client`, `socket`).
- **`project_index.py`:** Standard library `sqlite3` utilizing ACID transactions and `FTS5` full-text search.
- **`project_dependencies.py`:** Tarjan's Strongly Connected Components (SCC) and BFS traversal algorithms implemented natively in Python.
- **`blueprint_parser.py`:** Pure Python S-expression tokenizer and recursive-descent AST builder.

---

## 3. Security Architecture & Boundary Invariants

1. **Loopback-Only Invariant:**
   - Both Windows and macOS adapters enforce `-ini:Engine:[HTTPServer.Listeners]:DefaultBindAddress=127.0.0.1` on launch.
   - `guard_listener_overrides` rejects wildcard addresses (`0.0.0.0`, `::`) and public IP bindings before allowing configuration.
2. **Safe Argument Construction:**
   - Subprocess executions use strict argument arrays (e.g. `[editor_exe, project_path, ...]`) rather than shell string concatenation (`shell=False`), preventing shell injection attacks even when project paths contain spaces or special characters.
3. **Readback Verification Gate:**
   - Before any scene mutation is executed, the two-factor project identity check must pass.
   - If listener ownership is ambiguous (multiple listeners or unidentified processes), all write tools are blocked.

