# Unreal Codex Bridge — ARC 02 Competitor & Reference Architecture Analysis

**Document Version:** 1.0.0  
**Date:** 2026-11-21  
**Milestone:** ARC 02 Phase 2  
**Target:** OpenAI Codex & Unreal Engine 5.8.4  
**Author:** Principal Unreal Engine Integration Engineer & Software Quality Lead  

---

## 1. Executive Summary

Before implementing the ARC 02 Project Intelligence, Asset Dependency Graph, and Context Retrieval engine for the **Unreal Codex Bridge**, we conducted a systematic technical investigation of six external open-source projects operating in the Unreal Engine AI / MCP ecosystem.

The objective was not to replace our verified, non-destructive architecture (which relies on Epic Games' native `ModelContextProtocol` and `AllToolsets` engine plugins in UE 5.8), but to analyze how other systems approach:
1. **Persistent project indexing** across large asset libraries.
2. **Token-efficient context retrieval** for LLM coding agents.
3. **Blueprint AST & graph parsing** without bloating LLM context windows.
4. **Asset dependency & referencer analysis**.
5. **Safety verification loops (readbacks)** and mutation boundaries.

---

## 2. Investigated Reference Projects

### 2.1 Primary References

#### 1. `qiqt/unreal-mcp` (GitHub: `https://github.com/qiqt/unreal-mcp`)
- **Focus:** Model Context Protocol server targeting Unreal Engine 5.6–5.8 with a dedicated focus on token-efficient Blueprint reading/editing and persistent project indexing.
- **Observed Architecture:**
  - Implements an external bridge process communicating with Unreal via socket/HTTP.
  - Maintains a local metadata cache of the project structure to avoid rescanning `/Game` on every LLM prompt.
  - Generates summarized Blueprint representations that condense node graphs into human/LLM-readable structures.
- **License:** Open Source (MIT-style / Community).
- **Lessons Adopted:**
  - *Adopt:* Persistent local indexing using SQLite to eliminate repetitive, slow MCP roundtrips over HTTP.
  - *Adopt:* Separate high-level summaries from deep pin-level graphs to conserve token budget.
- **Approaches Rejected:**
  - *Reject:* Custom standalone C++ plugins or proprietary socket servers. Epic's native UE 5.8 `ModelContextProtocol` plugin is already embedded and supported by Epic; introducing an alternate C++ plugin creates maintenance divergence and engine version friction.

#### 2. `Tractatuz/ue-agent-toolkit` (Codex Branch)
- **Status & Availability:** The repository handle `Tractatuz/ue-agent-toolkit` was queried across GitHub and web indexes. It is currently private or restricted.
- **Community Equivalent Investigated:** `timargv/UnrealMCPToolkit` and `bradenleague/UE-Agent-Asset-Toolkit`.
- **Observed Architecture:**
  - Offline `.uasset` binary inspection without launching the full Unreal Editor.
  - Skill organization designed around prompt-based tool dispatching.
- **Lessons Adopted:**
  - *Adopt:* Multi-tiered skill organization where low-level tools are wrapped in domain-specific agent skills (`unreal-mcp`, `create-toolset`).
- **Approaches Rejected:**
  - *Reject:* Offline binary parsing of `.uasset` files. Unreal's asset serialization format changes across engine versions (UE 5.3 -> 5.8). Parsing binaries offline outside the editor is fragile and risks data corruption. Epic's in-editor `AssetTools` and `AssetRegistry` provide 100% authoritative reflection.

#### 3. `CarlxsMG/UEAgent` (GitHub: `https://github.com/CarlxsMG/UEAgent`)
- **Focus:** Extensive in-editor MCP server plugin for UE 5.7/5.8 exposing over 1,500 granular tools with a strict verification/readback loop.
- **Observed Architecture:**
  - Operates directly inside the editor process, listening on `127.0.0.1`.
  - Implements an explicit **Readback Mechanism**: after any state mutation (spawning an actor, setting a property, modifying a node), it immediately queries the editor to verify that the change took effect and matches desired values.
  - Categorizes tools with precondition safety checks to prevent editor crashes or freezing.
- **License:** Source-available / Community (check repository for commercial terms).
- **Lessons Adopted:**
  - *Adopt:* The Readback Verification Principle. Every write or modify operation must be followed by an authoritative reflection query confirming state persistence.
  - *Adopt:* Precondition validation: refuse operations with malformed inputs before invoking engine APIs.
- **Approaches Rejected:**
  - *Reject:* Implementing a 1,500+ tool custom plugin. Epic Games' native `AllToolsets` already provides 53 toolsets and 832 tools directly in UE 5.8. Adding another monolithic C++ plugin duplicates functionality and complicates project distribution.

---

### 2.2 Secondary References

#### 4. `WildCake/unreal-engine-mcp-codex` (GitHub: `https://github.com/WildCake/unreal-engine-mcp-codex`)
- **Focus:** Codex-specific skill and configuration package built explicitly on top of Epic's native UE 5.8 Model Context Protocol server.
- **Key Characteristics:** Uses native `list_toolsets`, `describe_toolset`, and `call_tool`. Highly aligned with our architectural strategy.
- **Lessons Adopted:** Focus on Codex CLI compatibility, TOML registration, and leveraging Epic's official toolset namespaces.

#### 5. `FunplayAI/funplay-unreal-mcp` (GitHub: `https://github.com/FunplayAI/funplay-unreal-mcp`)
- **Focus:** Standalone workbench MCP server for UE5 game development, emphasizing `execute_python`, runtime screenshots, and Play-In-Editor (PIE) automation.
- **Lessons Adopted:** PIE lifecycle monitoring via `EditorAppToolset.IsPIERunning`, `StartPIE`, and `StopPIE`.

#### 6. `db-lyon/ue-mcp` (GitHub: `https://github.com/db-lyon/ue-mcp`)
- **Focus:** Popular open-source UE5 MCP server toolkit with extensive multi-agent and tool coverage.
- **Lessons Adopted:** Comprehensive error categorization and clear separation between read and write operations.

---

## 3. Comparative Capability Matrix

| Feature / Architecture | Epic Native UE 5.8 MCP | `qiqt/unreal-mcp` | `CarlxsMG/UEAgent` | `WildCake/unreal-codex` | **Unreal Codex Bridge (Ours)** |
|:---|:---:|:---:|:---:|:---:|:---:|
| **Engine Footprint** | Native (Zero custom C++) | Custom C++ Plugin | Custom C++ Plugin | Native (Zero custom C++) | **Native (Zero custom C++)** |
| **Target Engine** | UE 5.8.4 | UE 5.6–5.8 | UE 5.7–5.8 | UE 5.8+ | **UE 5.8.4 (CL 58902052)** |
| **Transport** | Streamable HTTP / SSE | Sockets / HTTP | In-editor Streamable HTTP | Streamable HTTP / SSE | **Streamable HTTP / SSE (Loopback)** |
| **Listener Security** | Default (Needs INI config) | Unauthenticated | Localhost binding | Loopback binding | **RFC Loopback Guards (`guard_listener_overrides`)** |
| **Process Identity Guard** | None | None | None | Basic | **Two-Factor (PowerShell CIM + Startup Logs)** |
| **Toolset Count** | 53 toolsets (832 tools) | Proprietary subset | ~1,500 tools | Native toolsets | **53 native toolsets (Dynamic on-demand)** |
| **Persistent Indexing** | None (Real-time queries) | Custom JSON/DB cache | None | None | **SQLite 3 + FTS5 Full-Text Indexing** |
| **Dependency Graph** | Raw API queries | Asset lookup | Asset lookup | None | **Full Directed Graph (Tarjan SCC, Cycles, Depth)** |
| **Blueprint Parsing** | Raw S-expression DSL | Token-optimized AST | Native toolset API | S-expression docs | **Native DSL Parser & AST Summary Engine** |
| **Context Digest** | None | Basic summaries | Activity log | None | **Token-budgeted Markdown Digest (`project_digest.md`)** |
| **Verification Loop** | Manual | Basic | Explicit Readback | Manual | **Readback Verification in Live Tests** |
| **Codex CLI Native** | No | Partial | Generic MCP | Yes | **Full (`resolve_codex_bin`, TOML, Skill)** |

---

## 4. Key Architectural Decisions for ARC 02

Based on this research, we established five definitive design decisions:

1. **Standard Library SQLite with FTS5 for Persistent Indexing:**
   Rather than keeping an in-memory dictionary or ad-hoc JSON files (which become slow and memory-intensive on 50,000-asset projects), we use Python's built-in `sqlite3` with an FTS5 full-text search table. This enables sub-millisecond keyword, variable, and function lookups without external Python package dependencies.
2. **Deterministic Adjacency Graph for Asset Dependencies:**
   Rather than querying Epic's `AssetTools.get_dependencies` repeatedly during LLM reasoning turns, we construct forward and reverse adjacency tables in the SQLite database. We apply Tarjan's Strongly Connected Components (SCC) algorithm to detect circular dependencies and assess blast radius before modifying core assets.
3. **Dedicated Read-Only AST Parser for Epic's Blueprint Graph DSL:**
   Epic's UE 5.8 MCP exposes `read_graph_dsl`, returning Lisp-style S-expressions. Instead of dumping raw S-expressions into LLM context (which wastes tokens and confuses agents), our parser extracts high-level semantic nodes: Events, Functions, Local Variables, Calls, and Control Flow edges.
4. **Strict Separation of Inspection from Mutation:**
   Under ARC 02, write tools (`BlueprintTools.write_graph_dsl`, `AssetTools.save_assets`, `SceneTools.remove_from_scene`) are strictly forbidden. The system is provably read-only.
5. **Configurable Token-Budgeted Digest Generation:**
   AI agents operate within strict context limits. Our digest generator (`generate_project_digest.py`) produces layered, hierarchical Markdown context with configurable budgets so Codex receives exactly what it needs for the task at hand.

