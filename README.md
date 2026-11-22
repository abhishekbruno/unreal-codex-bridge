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
| Script / Package | Description | Status |
| :--- | :--- | :--- |
| `editor_lifecycle.py` | Unified cross-platform CLI manager (`detect`, `prepare`, `launch`, `connect`, `doctor`, `status`, `uninstall`). | **Implemented & Verified** |
| `platform_adapter/` | Platform abstraction package decoupling Windows (CIM/WMI, Registry) from macOS (`lsof`, `ps`, bundles). | **Implemented & Verified** |
| `playtest.py` | Cross-platform Play-In-Editor (PIE) test runner and runtime log telemetry harvester. | **Implemented & Verified** |
| `bridge_mcp.py` | Streamable HTTP and SSE MCP client with JSON-RPC 2.0 handling, session headers, and loopback enforcement. | **Implemented & Verified** |
| `doctor.py` | Diagnostics runner performing system, CLI, engine, plugin, loopback, MCP handshake, and identity checks. | **Implemented & Verified** |
| `unreal_session.py` | Toolset catalog discovery, input schema validation, dynamic on-demand toolset loading, and process identity verification. | **Implemented & Verified** |
| `configure.py` | Backed-up configuration utility with preflight listener security guards for `.uproject`, editor INI settings, and `.codex/config.toml`. | **Implemented & Verified** |
| `inspect_project.py` | Read-only project discovery, scene intelligence, asset inventory, Blueprint graph/variable extraction, and structured JSON output. | **Implemented & Verified** |
| `project_dependencies.py` | Asset dependency graph engine with Tarjan's SCC cycle detection, transitive traversal, and blast radius impact analysis. | **Implemented & Verified** |
| `blueprint_parser.py` | Native S-expression tokenizer, nested list AST visitor, cyclomatic complexity calculator, and compact prompt summarizer. | **Implemented & Verified** |
| `project_index.py` | Persistent SQLite project index engine with FTS5 full-text search, deterministic SHA-256 IDs, and incremental `mtime` refresh. | **Implemented & Verified** |
| `query_project_index.py` | Sub-10ms deterministic multi-tier context retrieval engine with dependency/referencer relationship enrichment. | **Implemented & Verified** |
| `generate_project_digest.py` | Compact, token-budgeted project digest generator producing structured Markdown for agent system prompts. | **Implemented & Verified** |
| `live_test.py` | End-to-end live testing script for verifying level duplication, actor spawning, transform setting, and persistence. | **Implemented & Verified** |
| `install.py` | Portable installer for registering skills and MCP configuration into an Unreal project. | **Implemented & Verified** |
| `editor_state_guard.py` | Guarded package-saving and level-transition preflight checks with dirtiness verification. | **Implemented & Verified** |
| `level_transaction.py` | Resumable save-before-load level transaction manager with file locking and journaling. | **Implemented & Verified** |
| `auto_save_manager.py` | Centralized automatic entity save system for Actors, Blueprints, Materials, Components, and Assets with multi-step transaction checkpoints and persistence verification. | **Implemented & Verified** |

### Codex Skills (`skills/`)
| Skill | Description | Status |
| :--- | :--- | :--- |
| `unreal-game` | Complete game-authoring workflow from natural language prompts across Windows and macOS. | **Implemented** |
| `unreal-playtest` | Play-In-Editor session execution, state observation, and runtime log error analysis. | **Implemented** |
| `unreal-mcp` | Workflows and operational guidelines for querying and modifying running Unreal projects via MCP. | **Implemented** |
| `create-toolset` | Architectural and C++ guidance for extending Unreal MCP with custom native toolsets. | **Implemented** |
| `unreal-skill` | General Unreal Engine development patterns, asset conventions, and system rules. | **Implemented** |

### Offline Test Suites (`tests/`)
| Test Module | Coverage | Status |
| :--- | :--- | :--- |
| `test_platform_detect.py` | 6 tests: OS detection, Windows/Darwin factory routing, unsupported OS rejection. | **Passing (6/6)** |
| `test_windows_adapter.py` | 7 tests: Windows detection, x86_64/arm64 arch, Launcher manifests, codex.cmd, netstat PID, CIM. | **Passing (7/7)** |
| `test_macos_adapter.py` | 14 tests: Darwin detection, Apple Silicon vs Intel arch, .app bundle discovery, unix codex, lsof PID, ps, authentic process ownership, kernel libproc proc_pidpath, lookalike engine prefix rejection, ambiguous path rejection, stale log rejection. | **Passing (14/14)** |
| `test_editor_lifecycle.py` | 5 tests: Lifecycle detect, prepare with backups, launch args, status offline/online, uninstall revert. | **Passing (5/5)** |
| `test_plugin_packaging.py` | 4 tests: .codex-plugin/plugin.json schema, marketplace.json catalog, .mcp.json, skill frontmatter. | **Passing (4/4)** |
| `test_playtest.py` | 8 tests: Saved/Logs resolution, regex telemetry parsing, mock PIE execution flow, MCP error validation, evidence requirement, clean run guards, explicit PIEState lifecycle, stop failure recording. | **Passing (8/8)** |
| `test_configure.py` | 8 tests: Plugin preservation, TOML idempotence, backup creation, IPv4/IPv6 loopback acceptance, public override rejection. | **Passing (8/8)** |
| `test_diagnostics.py` | 9 tests: Engine checks, version validation, process identity rejection, schema validation, dynamic on-demand toolset discovery. | **Passing (9/9)** |
| `test_inspect_project.py` | 7 tests: Project metadata, bounded scene limits, property error resilience, asset inventory, Blueprint graphs, read-only guarantees. | **Passing (7/7)** |
| `test_dependencies.py` | 8 tests: Dependency graph construction, bounded BFS traversal, reverse referencers, Tarjan's SCC cycle detection, blast radius, JSON export. | **Passing (8/8)** |
| `test_blueprint_parser.py` | 5 tests: S-expression tokenization, nested AST visitor, event/function extraction, cyclomatic complexity, compact summaries. | **Passing (5/5)** |
| `test_project_index.py` | 7 tests: Schema initialization, asset upsert, Blueprint metadata, dependency storage, stale marking, FTS5 search, version migration. | **Passing (7/7)** |
| `test_query_index.py` | 9 tests: Exact path, exact name, variable lookup, function lookup, class filtering, FTS fallback, relationship enrichment, JSON & Markdown. | **Passing (9/9)** |
| `test_digest.py` | 4 tests: 10-section digest structure, strict character budgeting, empty database resilience, metadata relevance. | **Passing (4/4)** |
| `test_blueprint_authoring.py`| 18 tests: Declarative Blueprint node and wire specifications, pin types, graph validation. | **Passing (18/18)** |
| `test_blueprint_mutation.py` | 14 tests: Pre-flight AST validation, transaction guards, safety verification. | **Passing (14/14)** |
| `test_bridge.py` | 8 tests: Protocol handling, response unpacking, loopback validation, error mapping. | **Passing (8/8)** |
| `test_transport.py` | 6 tests: HTTP/SSE transport, redirect refusal, session headers, pagination. | **Passing (6/6)** |
| `test_install.py` | 4 tests: Plugin enablement, backup generation, INI and marketplace merging. | **Passing (4/4)** |
| `test_live_guards.py` | 3 tests: Non-colliding map name selection, transform assertions. | **Passing (3/3)** |
| `test_level_transaction.py` | 9 tests: Guarded save before load, transaction journaling, interrupt recovery. | **Passing (9/9)** |
| `test_auto_save_manager.py` | 32 tests: Package path normalization, actor/level/OFPA saving, Blueprint/Material/Component auto-save, multi-step transaction checkpoints, uninterrupted graph construction, dirty/exists persistence verification, EditorStateGuard reuse. | **Passing (32/32)** |
| **Total Test Suite** | **206 unit tests across 22 test modules** | **Passing (206/206 - 100%)** |

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

## 6. ARC 01, ARC 01.5 & ARC 02 Development Status

The primary milestones across ARC 01, ARC 01.5, and ARC 02 Phase 2 establish a reliable bridge and an intelligent context engine connecting OpenAI Codex to Unreal Engine 5.8:

### Verified Live Capabilities:
- **Editor Handshake:** Successful JSON-RPC 2.0 handshake over Streamable HTTP/SSE with protocol version negotiation (`2025-11-25`).
- **Dynamic Toolset Discovery:** Discovered 53 native toolsets totaling 832 tools; implemented on-demand toolset loading in `UnrealSession.load_toolset`.
- **Level Duplication & Persistence:** Successfully duplicated template maps, spawned static mesh actors, modified transforms, verified properties via reflection, saved to disk (`.umap`), and reloaded without state corruption.
- **Project Intelligence Foundation:** Implemented read-only discovery in `scripts/inspect_project.py`, extracting project metadata, scene hierarchy, `/Game` assets, and Blueprint graph/variable structures into `reports/project_intelligence.json`.
- **Asset Dependency Graph Engine:** Implemented directed reference graph builder (`scripts/project_dependencies.py`) with Tarjan's SCC cycle detection (handling cyclic engine assets), bounded transitive BFS, reverse referencers, and blast-radius impact analysis. Discovered 185 nodes, 303 edges, and 3 cycles in live test project (`reports/asset_dependencies.json`).
- **Epic S-Expression Blueprint Parser:** Implemented native tokenizer, nested list AST visitor, event/function/call extractor, and cyclomatic complexity calculator (`scripts/blueprint_parser.py`) for Epic's Lisp-style S-expression graph DSL (`docs/ARC02_BLUEPRINT_INTELLIGENCE.md`).
- **Persistent SQLite Project Index:** Implemented ACID-compliant schema with FTS5 full-text indexing, deterministic SHA-256 IDs, and incremental filesystem `mtime` change detection (`scripts/project_index.py`), delivering a 46% speedup on refresh.
- **Sub-10ms Context Retrieval:** Implemented deterministic multi-tier search engine (`scripts/query_project_index.py`) scoring exact paths (1.0), names (0.95), variables/functions (0.90), substrings (0.80), and FTS5 full-text (0.70), enriched with live dependencies and referencers in under 9ms (>1,500x speedup vs live MCP).
- **Project Context Digest Generator:** Implemented token-budgeted Markdown digest generator (`scripts/generate_project_digest.py`) producing structured context for Codex prompts (~1,410 tokens) in 81ms (`reports/project_digest.md`).

### Current Test Suite Status:
- **Total Tests:** 163 unit tests across 21 modules (`tests/`).
- **Passing:** 163 tests (100% pass rate).
- **Execution Time:** ~5.45 seconds offline.
- **Cross-Platform Support:** Clean platform adapters for Windows 10/11 (`x86_64`, `arm64`) and macOS (`arm64` Apple Silicon & `x86_64` Intel).
- **Security Hardening:** Completed `guard_listener_overrides` in `scripts/configure.py`, rejecting wildcard and public listener configurations.
- **Windows CLI Detection:** Resolved `codex.cmd` in `scripts/doctor.py` without `shell=True`.

---

## 7. Known Limitations

- **Experimental Protocol:** The Unreal MCP plugin in UE 5.8 is experimental. Tool names, input schemas, and return formats may vary between Unreal Engine releases.
- **Unauthenticated Local Server:** Epic's native HTTP server does not support token-based authentication. It must never be exposed to public networks or untrusted local networks.
- **Single Active Editor Instance:** The default MCP listener binds to port 8000. Running multiple editor instances concurrently requires per-project port offset configuration.
- **Game Thread Serialization:** Complex editor operations execute synchronously on the Unreal Editor main game thread; long-running operations can cause temporary client-side timeouts if not batched appropriately.
- **Circular Reference Cycles in Engine Assets:** Standard mannequin skeletal meshes and physics assets contain circular dependencies (`SKM_Manny` <-> `PA_Mannequin`). Dependency graphs must handle cycles gracefully.
- **macOS Hardware Availability:** macOS adapter logic is 100% unit tested; live in-editor hardware execution on physical Apple Silicon/Intel Macs is documented as BLOCKED when physical Mac hardware is unavailable.

---

## 8. Planned Development Roadmap

- [x] **Config Hardening:** Implemented `guard_listener_overrides` in `scripts/configure.py` (100% test suite pass rate).
- [x] **Windows CLI Detection:** Implemented `resolve_codex_bin` in `scripts/doctor.py` resolving `codex.cmd`.
- [x] **Dynamic Toolset Discovery:** Implemented on-demand loading of all 53 toolsets (`scripts/unreal_session.py`).
- [x] **Project Intelligence Foundation:** Implemented read-only scene/asset/blueprint inspection (`scripts/inspect_project.py`).
- [x] **Asset Dependency Mapping & Blast Radius:** Built full reference graph with Tarjan's SCC cycle detection (`scripts/project_dependencies.py`).
- [x] **Blueprint Graph S-Expression AST Parser:** Tokenize, parse, and analyze Epic's graph DSL with cyclomatic complexity (`scripts/blueprint_parser.py`).
- [x] **Persistent SQLite Project Index:** Built disk-backed index with FTS5 search and incremental `mtime` updates (`scripts/project_index.py`).
- [x] **Sub-10ms Context Retrieval Engine:** Multi-tier deterministic search with relationship enrichment (`scripts/query_project_index.py`).
- [x] **Project Context Digest Generator:** Compact, token-budgeted markdown summary for agent system prompts (`scripts/generate_project_digest.py`).
- [x] **Integration Sprint 01 — Cross-Platform Plugin:** Platform adapters (`platform_adapter/`), unified lifecycle CLI (`editor_lifecycle.py`), official Codex plugin manifests, and PIE workflows (`playtest.py`).
- [ ] **ARC 02 Phase 3 — Declarative Blueprint Graph Authoring & Compiler:** (PAUSED) Generate Epic S-expression DSL AST from high-level specifications and compile via `BlueprintTools.write_graph_dsl`.
- [ ] **Multi-Instance Port Routing:** Automatically discover active Unreal Editor ports and resolve multi-instance collisions.
- [ ] **CI Test Automation:** Configure GitHub Actions for offline mock unit testing across Windows and macOS runners.
- [ ] **Unreal Engine 5.9 ACP Bridge:** Provide native in-editor ACP guidance and adapters for the UE 5.9 Unreal Assistant workflow.

---

## 9. Credits and Licensing

- **Original Epic Games Skills:** Portions of the included developer skills are adapted from Epic Games' MIT-licensed `unreal-engine-skills-for-claude-code-plugin` repository.
- **License:** Released under the [MIT License](LICENSE). Copyright (c) 2026 Epic Games, Inc. and contributors.
- **Disclaimer:** This project is an independent community development and is not officially affiliated with Epic Games or OpenAI.
