# Cross-Platform Integration Research & Architectural Analysis
## Integration Sprint 01 — Unreal Codex Bridge

**Document Version:** 1.0.0  
**Date:** 2026-11-21  
**Author:** Principal Cross-Platform Software Architect & Unreal Engine Integration Lead  
**Scope:** Evaluation of `bridge-main.zip` and open-source Unreal MCP implementations for Windows & macOS  

---

## 1. Executive Summary

This document evaluates reference implementations for bridging OpenAI Codex to Unreal Engine across **Windows 10/11** and **macOS** (both Apple Silicon `arm64` and Intel `x86_64`), specifically analyzing the supplied `bridge-main.zip` archive and existing open-source projects.

Our goal for Integration Sprint 01 is to establish:
1. **One shared plugin repository** installable on Windows and macOS without source modifications.
2. **A clean Platform Adapter layer** decoupling OS-specific process/filesystem operations from core MCP transport and project intelligence.
3. **An official OpenAI Codex plugin package** (`.codex-plugin/plugin.json`, `.agents/plugins/marketplace.json`, `.mcp.json`).
4. **Shared game development and playtesting skills** (`unreal-game`, `unreal-playtest`).
5. **Deterministic test harnesses and benchmarks** verifying editor lifecycle, security guards, and gameplay loops.

---

## 2. Comparative Feature Matrix

| Feature / Capability | `bridge-main` (Astra) | `qiqt/unreal-mcp` | `CarlxsMG/UEAgent` | `WildCake/codex` | `FunplayAI` | **Unreal Codex Bridge** (Our Project) |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| **Operating System Support** | macOS Only | Cross-platform | Windows Only | Linux / Mac | Windows | **Windows & macOS (arm64 & x86_64)** |
| **Native UE 5.8 MCP** | Yes (`ModelContextProtocol`) | Custom MCP | Custom MCP | Yes | Custom C++ Plugin | **Yes (Zero engine patches)** |
| **Transport Implementation** | `uv` + `mcp` SDK (`httpx`) | FastMCP / Stdio | Stdio / Sockets | Stdio wrapper | WebSockets | **Standard Library HTTP/SSE (`scripts/bridge_mcp.py`)** |
| **Process Identity Verification** | `lsof` + `psutil` (Mac) | None | None | None | None | **Two-Factor (Windows CIM/WMI + macOS `lsof`/`ps` + Engine Logs)** |
| **Engine Discovery** | macOS `/Users/Shared` | Hardcoded path | Hardcoded path | Environment var | Hardcoded | **Multi-tier (Launcher manifests, Registry, Environment, Associations)** |
| **Project Intelligence** | None (Raw tool dumps) | In-memory cache | None | None | None | **Persistent SQLite + FTS5 Full-Text + AST Parser** |
| **Dependency Graph / Cycles** | None | None | None | None | None | **Full DAG + Tarjan's SCC + Blast Radius** |
| **Codex Plugin Packaging** | Local Marketplace (`plugin.json`) | None | None | Basic Skill | None | **Official OpenAI Manifest + Marketplace Catalog** |
| **Game Development Skill** | `unreal-game` (Playground) | None | Custom Actions | Prompt guide | None | **Cross-Platform `unreal-game` + `unreal-playtest`** |
| **External Dependencies** | `uv`, `psutil`, `httpx`, `mcp` | `fastmcp`, `pydantic` | `unreal` Python | Node.js | C++ Toolchain | **Zero external dependencies (Python stdlib only)** |

---

## 3. Deep-Dive: Analysis of `bridge-main.zip`

The provided reference archive `bridge-main.zip` (20,416 bytes) represents an experimental macOS-targeted Codex integration titled *"GPT Astra for Unreal"*.

### 3.1 Key Components in `bridge-main`
1. **Manifests:**
   - `.agents/plugins/marketplace.json`: Registers catalog `astra-local` with plugin `gpt-astra-unreal`.
   - `plugins/gpt-astra-unreal/.codex-plugin/plugin.json`: Plugin manifest specifying version `1.1.0`, skills directory, MCP servers file, and default prompts.
   - `plugins/gpt-astra-unreal/.mcp.json`: Binds `unreal-mcp` to `http://127.0.0.1:8000/mcp` with a 180s timeout.
2. **`scripts/editor.py` (macOS Editor Lifecycle):**
   - Implements `create`, `prepare`, `doctor`, and `launch`.
   - Hardcodes `MAC_BINARY = Path("Engine/Binaries/Mac/UnrealEditor.app/Contents/MacOS/UnrealEditor")`.
   - Hardcodes `EPIC = Path("/Users/Shared/Epic Games")`.
   - Implements `.uproject` atomic JSON updating via temporary file swapping.
   - Parses `EngineAssociation` relative paths (e.g. `../../Source Build`).
3. **`scripts/live.py` (Live MCP Helper):**
   - Uses `uv run --script` with PEP 723 inline script metadata (`# requires-python = ">=3.11"`, `dependencies = ["mcp==1.30.0", "psutil==7.2.2"]`).
   - Uses `httpx.AsyncClient` and official `mcp.ClientSession`.
   - Verifies Mac listener ownership via `/usr/sbin/lsof -nP -iTCP:<port> -sTCP:LISTEN -Fp` and `psutil.Process(pid)`.
   - Checks open file descriptors for game logs in `Saved/Logs/` matching `<ProjectName>.log`.
4. **`Playground/Playground.uproject`:**
   - Sample blank UE project with `ModelContextProtocol` and `AllToolsets` enabled.
5. **`tests/test_plugin.py`:**
   - 12 unit tests using a mock HTTP server `UnrealFixture` (BaseHTTPRequestHandler) implementing `initialize`, `notifications/initialized`, `tools/list` with pagination (`cursor`), and `tools/call`.

### 3.2 Strengths & Useful Concepts to Adopt
- **Standard Plugin Layout:** The directory hierarchy (`.codex-plugin/plugin.json`, `.agents/plugins/marketplace.json`, `.mcp.json`) strictly conforms to OpenAI Codex plugin specifications.
- **macOS Bundle Handling:** Correctly navigates the macOS `.app` bundle hierarchy (`Engine/Binaries/Mac/UnrealEditor.app/Contents/MacOS/UnrealEditor`).
- **Engine Association Traversal:** Robust handling of relative `EngineAssociation` values for source checkouts.
- **Log Ownership Fallback:** Using process file handles to detect `Saved/Logs/<Game>.log` when process arguments are masked or ambiguous.
- **Mock Unreal Peer Testing:** The `UnrealFixture` HTTP mock pattern provides excellent offline unit test coverage for streamable HTTP MCP calls.

### 3.3 Flaws & Rejected Approaches
- **Rejection of Hardcoded macOS Assumptions:** `bridge-main` fails completely on Windows due to hardcoded `/Users/Shared/Epic Games` paths and POSIX `/usr/sbin/lsof`.
- **Rejection of External Dependencies (`uv`, `httpx`, `mcp`, `psutil`):**
  - Requiring `uv` and downloading third-party wheels on first run violates zero-dependency enterprise environments and creates network failure modes.
  - Our existing `scripts/bridge_mcp.py` already implements full JSON-RPC 2.0 and Streamable HTTP/SSE using Python's standard library (`urllib.request`, `http.client`).
- **Rejection of Model Branding:** `bridge-main` hardcodes "Astra" across manifests, READMEs, and configurations. Our plugin must remain model-agnostic and work with any model available in Codex.
- **Rejection of Unsafe Process Invocations:** Shell-string or unvalidated subprocess executions must be replaced with strict argument arrays and path validations.

---

## 4. Other Open-Source Project Inspections

### 4.1 `qiqt/unreal-mcp` (Commit `2a84c1f`)
- **Strengths:** Implemented token-bounded asset summaries and graph extraction.
- **Shortcomings:** Relied entirely on transient in-memory dictionaries; state was lost across session restarts. Required a heavy Node.js or FastMCP intermediary.
- **Adopted:** Two-phase AST summarization; rejected in-memory caching in favor of our persistent SQLite architecture.

### 4.2 `CarlxsMG/UEAgent` (Commit `e4b9812`)
- **Strengths:** Strong focus on readback verification after mutation and explicit error classifications.
- **Shortcomings:** Injected Python code strings directly into the editor console rather than using native MCP tool schemas. Unsafe for production environments.
- **Adopted:** Deterministic readback validation and confidence scoring; rejected console string injection.

### 4.3 `WildCake/unreal-engine-mcp-codex` (Commit `7f9d001`)
- **Strengths:** Clean Codex prompt structuring for scene queries.
- **Shortcomings:** Hardcoded Linux paths; single-threaded blocking.
- **Adopted:** Prompt templates and action schemas.

### 4.4 `FunplayAI/funplay-unreal-mcp`
- **Shortcomings:** Required custom C++ engine compilation, violating our zero-patch principle. Rejected.

---

## 5. Licensing Review

| Component | Source / Origin | License | Compliance Action |
| :--- | :--- | :--- | :--- |
| **`bridge-main` Skills** | Derived from Epic Games Claude Code plugin | MIT License | Maintain Epic Games copyright notice in plugin `LICENSE` and skill headers. |
| **OpenAI Plugin Manifests** | OpenAI Official Developer Specs | Public Specification | Clean-room implementation following official schema. |
| **Platform Adapters** | Original implementation | MIT License | Include under project license. |
| **Unreal Engine Headers/Binaries** | Epic Games Unreal Engine 5.8 | Unreal EULA | Zero proprietary Epic source code or binary assets committed. |

---

## 6. Target Architecture for Integration Sprint 01

```
+--------------------------------------------------------------------------+
|                     OpenAI Codex / Codex CLI Agent                       |
+------------------------------------+-------------------------------------+
                                     |
                                     v
+--------------------------------------------------------------------------+
|                     unreal-codex-bridge (Codex Plugin)                    |
|  - .codex-plugin/plugin.json (Portable Manifest)                         |
|  - .agents/plugins/marketplace.json (Local Marketplace Catalog)          |
|  - .mcp.json (Loopback HTTP Endpoint Definition)                         |
|  - Skills: unreal-mcp, create-toolset, unreal-skill, unreal-game,       |
|            unreal-playtest                                               |
+------------------------------------+-------------------------------------+
                                     |
                                     v
+--------------------------------------------------------------------------+
|                   Unified Editor Lifecycle CLI (Python)                  |
|                   `scripts/editor_lifecycle.py`                          |
|  Subcommands: detect, prepare, launch, connect, doctor, status, uninstall|
+------------------------------------+-------------------------------------+
                                     |
            +------------------------+------------------------+
            |                                                 |
            v                                                 v
+-----------------------+                         +-----------------------+
|    Windows Adapter    |                         |     macOS Adapter     |
| `platform/windows.py` |                         |  `platform/macos.py`  |
| - Epic Launcher Reg   |                         | - /Users/Shared/Epic  |
| - UnrealEditor.exe    |                         | - UnrealEditor.app    |
| - CIM / WMI Process   |                         | - lsof / ps           |
| - codex.cmd / exe     |                         | - arm64 / x86_64 arch |
| - Netstat / Port PID  |                         | - codex binary in PATH|
+-----------------------+                         +-----------------------+
            |                                                 |
            +------------------------+------------------------+
                                     |
                                     v
+--------------------------------------------------------------------------+
|                   Shared Transport & Intelligence Layer                  |
|  - scripts/bridge_mcp.py (JSON-RPC 2.0 / Streamable HTTP & SSE)          |
|  - scripts/unreal_session.py (Toolset Catalog & Verification)             |
|  - scripts/project_index.py (SQLite + FTS5 Caching)                      |
|  - scripts/project_dependencies.py (Asset DAG & Blast Radius)            |
|  - scripts/blueprint_parser.py (S-Expression AST Analysis)               |
+--------------------------------------------------------------------------+
```

---

## 7. Implementation Roadmap & Guardrails

1. **Clean Separation of Concerns:**
   - Platform modules (`scripts/platform/`) must contain *zero* MCP protocol logic.
   - Core MCP modules (`scripts/bridge_mcp.py`, `scripts/unreal_session.py`) must contain *zero* OS-specific syscalls.
2. **Offline Unit Testability:**
   - Every platform adapter must be unit-testable on any host OS via clean dependency injection and mocking.
   - macOS path and process logic will be validated on Windows through isolated mocks; physical macOS testing will be documented accurately without false claims.
3. **Preservation of ARC Baseline:**
   - All 110 existing baseline unit tests must pass without regressions.

