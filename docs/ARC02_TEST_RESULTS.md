# Unreal Codex Bridge — ARC 02 Automated Test Results & Verification

**Document Version:** 2.0.0  
**Date:** 2026-11-21  
**Target:** OpenAI Codex & Unreal Engine 5.8.4  
**Test Suite Status:** 78 Passed, 0 Failed, 0 Skipped (100% Pass Rate)  
**Total Test Modules:** 12 Modules  
**Live Integration Tests:** All Passed  

---

## 1. Automated Test Execution Summary

The test discovery suite was executed using Python's standard `unittest` discovery runner (`python -m unittest discover -s tests -p "test_*.py"`).

```
..............................................................................
----------------------------------------------------------------------
Ran 78 tests in 4.913s

OK
```

---

## 2. Detailed Test Results by Module

### 2.1 `tests/test_configure.py` (Configuration & Security Guards — 8 tests)
- `test_backup_and_idempotence`: Verifies timestamped file backups and idempotent modifications. **PASS**
- `test_duplicates_and_conflicts_are_refused`: Ensures duplicate server registrations are rejected. **PASS**
- `test_existing_codex_is_byte_preserved`: Preserves untouched sections in `.codex/config.toml`. **PASS**
- `test_ini_preserves_other_sections`: Verifies Unreal INI comments and non-MCP sections are preserved. **PASS**
- `test_listener_overrides_comprehensive_security`: Tests rejection of `0.0.0.0`, `::`, public IPs, and non-loopback overrides; verifies `127.0.0.1` and `::1` loopback acceptance. **PASS**
- `test_new_registration_preserves_other_servers`: Verifies multi-server `.codex/config.toml` coexistence. **PASS**
- `test_plugins_preserve_other_entries_and_fields`: Ensures `.uproject` plugin array edits preserve existing plugins. **PASS**
- `test_public_port_override_rejected_before_configuration`: Verifies `guard_listener_overrides` blocks configuration when public bind addresses are present. **PASS**

### 2.2 `tests/test_diagnostics.py` (Diagnostics & Toolset Discovery — 9 tests)
- `test_status_exit_codes`: Tests doctor exit code mapping. **PASS**
- `test_missing_plugin_is_not_compatible`: Rejects projects missing required MCP plugins. **PASS**
- `test_wrong_version_rejected`: Rejects Unreal Engine versions other than 5.8. **PASS**
- `test_toolset_description_bullets_not_toolsets`: Verifies toolset markdown parsing. **PASS**
- `test_required_argument_and_type_validation`: Enforces JSON Schema type constraints. **PASS**
- `test_process_identity_rejects_same_name_other_directory`: Prevents spoofing Unreal process identity. **PASS**
- `test_dynamic_toolset_loading`: Validates on-demand loading of uncataloged toolsets (`BlueprintTools`). **PASS**
- `test_unknown_toolset_raises_mcperror`: Ensures unrecognized toolset names raise informative `MCPError`. **PASS**
- `test_missing_tool_in_toolset_raises_mcperror`: Ensures missing tool names within a toolset raise `MCPError` with available tools listed. **PASS**

### 2.3 `tests/test_bridge.py` (MCP Protocol & Transport — 8 tests)
- `test_accept_loopback`: Accepts loopback endpoints. **PASS**
- `test_reject_nonlocal_urls`: Rejects remote non-loopback URLs. **PASS**
- `test_html_not_mcp`: Rejects HTML server responses as non-MCP. **PASS**
- `test_project_path_normalized`: Validates filesystem path normalization across platforms. **PASS**
- `test_rpc_error_not_success`: Parses JSON-RPC error responses cleanly. **PASS**
- `test_sse_matching_response`: Matches SSE responses to client request IDs. **PASS**
- `test_wrong_project_rejected`: Enforces `.uproject` path matching between client and server. **PASS**
- `test_wrong_response_id_rejected`: Enforces request/response ID integrity. **PASS**

### 2.4 `tests/test_transport.py` (Low-Level HTTP & SSE Sessions — 6 tests)
- `test_closed_server_is_not_operational`: Detects unresponsive endpoints. **PASS**
- `test_error_tool_result_is_failure`: Detects `isError: true` tool responses. **PASS**
- `test_incorrect_endpoint_returns_transport_error`: Cleanly handles transport failures. **PASS**
- `test_no_redirect_to_remote_server`: Prevents HTTP 30x redirects to external hosts. **PASS**
- `test_real_http_session_headers_and_pagination`: Validates header negotiation and chunking. **PASS**
- `test_real_sse_initialization`: Validates Server-Sent Events handshake. **PASS**

### 2.5 `tests/test_install.py` (Installer & Auto-configuration — 4 tests)
- `test_autostart_updates_existing_section`: Tests INI auto-start command insertion. **PASS**
- `test_existing_config_and_marketplace_preserved`: Preserves marketplace plugins in `.uproject`. **PASS**
- `test_mcp_skill_frontmatter`: Verifies YAML frontmatter in installed Codex skills. **PASS**
- `test_project_plugins_backup_and_idempotence`: Verifies installer backup generation. **PASS**

### 2.6 `tests/test_live_guards.py` (Safety & Mutation Guards — 3 tests)
- `test_existing_map_is_never_reused`: Enforces dedicated map creation for write tests. **PASS**
- `test_first_run_uses_preferred_map`: Validates initial map naming convention. **PASS**
- `test_transform_exact_values`: Validates floating-point transform tolerance checks. **PASS**

### 2.7 `tests/test_inspect_project.py` (Project Intelligence Foundation — 7 tests)
- `test_inspect_project_metadata`: Verifies project name, engine build, and active level extraction. **PASS**
- `test_inspect_toolsets`: Verifies toolset discovery and catalog aggregation. **PASS**
- `test_inspect_scene_bounded_limits_and_structure`: Enforces actor count limits and outliner structure. **PASS**
- `test_inspect_scene_resilient_to_property_errors`: Ensures property lookup failures do not abort inspection. **PASS**
- `test_inspect_assets_bounded_limits`: Enforces asset count limits and class breakdown. **PASS**
- `test_inspect_blueprints`: Validates Blueprint graph, variable, and function extraction. **PASS**
- `test_read_only_safety_guarantee`: Proves zero mutate/write tools are invoked during inspection. **PASS**

### 2.8 `tests/test_dependencies.py` (Asset Dependency Graph Engine — 8 tests)
- `test_graph_construction`: Verifies directed node and edge insertions and statistics. **PASS**
- `test_transitive_dependencies_bounded`: Verifies bounded BFS traversal up to `max_depth`. **PASS**
- `test_transitive_referencers_bounded`: Verifies reverse traversal up to `max_depth`. **PASS**
- `test_cycle_detection_tarjan`: Detects cyclic references using Tarjan's SCC algorithm. **PASS**
- `test_blast_radius_impact_analysis`: Accurately classifies impact by depth and circular reference risk. **PASS**
- `test_isolated_nodes`: Validates orphan node discovery. **PASS**
- `test_export_json`: Verifies full JSON serialization and schema compliance. **PASS**
- `test_live_dependency_builder_mock`: Validates extraction of dependencies from mock `AssetTools.get_dependencies`. **PASS**

### 2.9 `tests/test_blueprint_parser.py` (Blueprint S-Expression AST Parser — 5 tests)
- `test_tokenize_basic`: Tokenizes parentheses, string literals, keywords, and symbols. **PASS**
- `test_parse_sexpr_ast`: Builds nested Python list AST from S-expression tokens. **PASS**
- `test_extract_blueprint_ast`: Extracts event definitions, function calls, local bindings, and control flow branches. **PASS**
- `test_cyclomatic_complexity`: Accurately counts branching points (`if`, `branch`, `switch`) to compute complexity. **PASS**
- `test_compact_summary`: Generates token-budgeted, concise Markdown summaries for Codex prompts. **PASS**

### 2.10 `tests/test_project_index.py` (Persistent SQLite Index Engine — 7 tests)
- `test_schema_initialization`: Initializes tables, FTS5 virtual tables, indexes, and metadata version. **PASS**
- `test_asset_upsert_and_fetch`: Verifies asset upsert, primary key integrity, and metadata retrieval. **PASS**
- `test_blueprint_upsert`: Stores and retrieves Blueprint graphs, variables, functions, and complexity. **PASS**
- `test_dependency_storage`: Stores and queries directed dependency edges. **PASS**
- `test_stale_data_marking`: Tracks incremental runs and cleans/marks deleted assets. **PASS**
- `test_fts5_search`: Verifies full-text search across asset names, paths, variables, and function names. **PASS**
- `test_schema_version_mismatch_rebuild`: Detects schema version increments and automatically migrates/rebuilds. **PASS**

### 2.11 `tests/test_query_index.py` (Search & Context Retrieval Engine — 9 tests)
- `test_exact_path_lookup`: Exact package path query with 1.0 confidence score. **PASS**
- `test_exact_name_lookup`: Exact asset name query with 0.95 confidence score. **PASS**
- `test_variable_lookup`: Locates assets containing named variables (`SpawnPoint`). **PASS**
- `test_function_lookup`: Locates assets containing named functions (`UpdateHealth`). **PASS**
- `test_class_filter`: Filters search results by `asset_class`. **PASS**
- `test_fts_fallback`: Full-text search fallback with ranking scores. **PASS**
- `test_relationship_enrichment`: Returns direct dependencies and incoming referencers in results. **PASS**
- `test_structured_json_output`: Verifies structured JSON serialization for agent consumption. **PASS**
- `test_format_search_markdown`: Formats search results into compact markdown with relationship summaries. **PASS**

### 2.12 `tests/test_digest.py` (Project Context Digest Generator — 4 tests)
- `test_digest_generation_structure`: Generates all 10 standard sections of the context digest. **PASS**
- `test_digest_character_budget`: Strictly respects the user-defined character budget limit. **PASS**
- `test_digest_empty_db`: Gracefully handles empty or newly initialized databases without crashing. **PASS**
- `test_digest_content_relevance`: Validates presence of critical project metadata, level names, and assets. **PASS**

---

## 3. Live Integration Test Evidence

### 3.1 Live Diagnostics (`scripts/doctor.py`)
- Verified engine: Unreal Engine 5.8.4 (CL 58902052)
- Verified active project: `D:\newpproject\UnrealCodexTest\UnrealCodexTest.uproject`
- Verified active listener PID: 23088
- Verified tool discovery: 53 toolsets, 832 tools
- Verified Codex CLI: `codex-cli 0.171.0` (resolved via `codex.cmd` on Windows)
- Exit code: `0 (ALL PASS)`

### 3.2 Live End-to-End Object Lifecycle (`scripts/live_test.py`)
- Test map created: `/Game/CodexBridgeTests/ARC01_TestLevel_003`
- Spawned actor: `StaticMeshActor_1` (Cube)
- Set label: `Codex_Test_Cube`
- Set transform: Location `(0, 0, 150)`, Rotation `(0, 0, 0)`, Scale `(1, 1, 1)`
- Saved level to disk: `ARC01_TestLevel_003.umap` (51,441 bytes)
- Reloaded level and verified actor persistence across reload
- Exit code: `0 (PASS)`

### 3.3 Live Project Intelligence (`scripts/inspect_project.py`)
- Output: `reports/project_intelligence.json` (74,323 bytes)
- Project identity verified
- Active level: `/Game/CodexBridgeTests/ARC01_TestLevel_003`
- Inspected 16 scene actors, 50 assets across 12 classes, and 8 Blueprints
- Extracted complete Blueprint graph, variable, and function trees
- Proved 0 mutations performed
- Exit code: `0 (PASS)`

### 3.4 Live Asset Dependency Graph (`scripts/project_dependencies.py`)
- Output: `reports/asset_dependencies.json` (185 nodes, 303 directed edges)
- Discovered 3 real engine circular dependency components:
  1. `SKM_Manny_Simple` <-> `PA_Mannequin`
  2. `SKM_Quinn_Simple` <-> `PA_Mannequin`
  3. `SKM_Manny` <-> `PA_Mannequin`
- Blast radius calculations tested across depths 1 through 3
- Exit code: `0 (PASS)`

### 3.5 Live Persistent Indexing (`scripts/project_index.py`)
- Database: `data/project_index.sqlite` (720,896 bytes)
- Cold index build: 60 assets, 11 Blueprints, 16 actors, 639 dependencies in 151.07s
- Incremental refresh: 60/60 unchanged assets skipped via `mtime` cache in 81.52s (46% faster)
- FTS5 full-text index populated and verified
- Exit code: `0 (PASS)`

### 3.6 Live Search & Retrieval (`scripts/query_project_index.py`)
- Query by variable (`--variable SpawnPoint`): Located `BP_SaveData` in **7.4 ms**
- Query by path (`--path /Game/UI/UI_InGame`): Located UI Widget Blueprint with 12 dependencies and 2 referencers in **8.1 ms**
- Query by name substring (`--search Manny`): Located 4 skeletal meshes with ranked relevance in **8.8 ms**
- Response time speedup vs live MCP tool call: **>1,500x faster**

### 3.7 Live Project Context Digest (`scripts/generate_project_digest.py`)
- Output: `reports/project_digest.md` (5,643 chars, 103 lines, ~1,410 tokens)
- Generation time: **0.081s**
- Fits completely within the standard Codex prompt context window (budget: 16,000 chars)
- Exit code: `0 (PASS)`
