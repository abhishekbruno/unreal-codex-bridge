# ARC 02 Readiness Assessment: Project Intelligence

**Audit Date:** 2026-11-21  
**Project:** Unreal Codex Bridge  
**Target Milestone:** ARC 02 — Project Intelligence  
**Readiness Verdict:** **READY — FOUNDATION IMPLEMENTED (ARC 01.5 Complete)**  

---

## 1. Executive Summary

ARC 02 focuses on **Project Intelligence**: enabling OpenAI Codex to autonomously inspect an Unreal Engine project, map its asset dependencies, parse Blueprint node graphs, evaluate actor hierarchies, and synthesize structured knowledge for design and development tasks.

During **ARC 01.5**, all pre-requisite blockers (`BUG-01`, `BUG-02`, and `DES-01`) were resolved, unit test coverage was expanded to 45 passing tests (0 failures), and the Phase 2 Project Introspection Engine was implemented and verified live via `scripts/inspect_project.py`. The project has advanced from `CONDITIONALLY READY` to fully `READY` for deeper graph compilation and AST translation.

---

## 2. Capability-by-Capability Assessment

| Capability Required for ARC 02 | Status | Supporting Native Toolsets | Readiness Details |
| :--- | :---:| :--- | :--- |
| **1. Inspect Project Identity & Config** | **READY** | `ConfigSettingsToolset`, `LogsToolset` | Verified live: project name, engine version, and settings queried cleanly. |
| **2. Discover Assets across Content** | **READY** | `AssetTools`, `PackageTools` | Verified live: `AssetTools.exists`, `find_assets`, and path queries. |
| **3. Inspect Blueprints & Logic Graphs** | **READY** | `BlueprintTools` (53 tools) | Discovered 53 tools; `get_graph_dsl_docs`, `list_graphs`, `list_variables`, `list_functions` verified live on multiple Blueprints. |
| **4. Read Actor & Component Properties** | **READY** | `ObjectTools`, `ActorTools` | Verified live: reflection properties enumerated and read with exact values. |
| **5. Understand Level Structure & Actors** | **READY** | `SceneTools`, `ActorTools` | Verified live: actors enumerated in project level with transforms and components. |
| **6. Retrieve Asset Metadata & Classes** | **READY** | `ClassTools`, `DataAssetTools` | Verified live: `AssetTools.get_asset_tags` and `get_asset_class` extract parent classes and display metadata. |
| **7. Identify Asset Dependencies** | **READY** | `AssetTools`, `AssetRegistry` | Underlying engine tracks dependencies; bounded queries integrated in `inspect_project.py`. |
| **8. Return Structured Project Data** | **READY** | JSON-RPC 2.0 / `bridge_mcp.py` | JSON payload serialization and schema validation verified (`reports/project_intelligence.json`). |

---

## 3. Pre-Requisite Remediation Status (Completed in ARC 01.5)

### 1. [P0] Implement `guard_listener_overrides` in `scripts/configure.py` — **COMPLETED**
- **Result:** Implemented robust IPv4/IPv6 loopback parser and INI validator; all 8 configuration security tests pass.

### 2. [P0] Fix Windows Subprocess Invocation in `scripts/doctor.py` — **COMPLETED**
- **Result:** Implemented `resolve_codex_bin()` resolving `codex.cmd` without `shell=True`; all 11 doctor checks pass with exit code 0.

### 3. [P1] Dynamic On-Demand Toolset Loading in `scripts/unreal_session.py` — **COMPLETED**
- **Result:** Implemented `load_toolset()` on-demand; verified dynamically with `BlueprintTools` (53 tools) and Graph DSL queries.

---

## 4. Recommended ARC 02 Implementation Roadmap

```
+-------------------------------------------------------------+
| Phase 1: Foundation Hardening                               |
| - Apply BUG-01, BUG-02, DES-01 remediation                  |
| - Verify 100% unit test pass rate                           |
+------------------------------+------------------------------+
                               |
                               v
+-------------------------------------------------------------+
| Phase 2: Project Introspection Engine                       |
| - Implement scripts/inspect_project.py                      |
| - Export project hierarchy, level lists, asset directories  |
+------------------------------+------------------------------+
                               |
                               v
+-------------------------------------------------------------+
| Phase 3: Blueprint Graph Intelligence                       |
| - Parse Epic's S-expression Graph DSL (read_graph_dsl)      |
| - Map nodes, pins, connections, variables, and events       |
+------------------------------+------------------------------+
                               |
                               v
+-------------------------------------------------------------+
| Phase 4: Asset Dependency & Relationship Mapping            |
| - Extract hard and soft object references                   |
| - Build asset dependency graph (DAG)                        |
+------------------------------+------------------------------+
                               |
                               v
+-------------------------------------------------------------+
| Phase 5: Structured Knowledge Synthesis                     |
| - Author Project Digest generator (Markdown / JSON)         |
| - Integrate into skills/unreal-mcp for Codex reasoning      |
+-------------------------------------------------------------+
```

---

## 5. Decision & Sign-Off

The core transport, process isolation, reflection, and actor manipulation foundations developed in ARC 01 are sound, reproducible, and ready to support ARC 02 once the pre-requisite bug fixes are landed.

