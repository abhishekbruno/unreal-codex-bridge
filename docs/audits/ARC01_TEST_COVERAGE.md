# ARC 01 Test Coverage & Verification Analysis

**Audit Date:** 2026-11-21  
**Project:** Unreal Codex Bridge  
**Milestone:** ARC 01  

---

## 1. Test Suite Overview

Testing for the Unreal Codex Bridge is structured into two distinct layers:
1. **Offline Mock Unit Test Suites:** Hermetic Python unit tests utilizing standard library fixtures, ephemeral HTTP servers, and temporary project mock directories. These validate protocol specifications, configuration parsing, safety guards, and error handling without requiring a running Unreal Editor instance.
2. **Live Integration Test Suites:** Live end-to-end verification scripts that connect over loopback HTTP/SSE to a running Unreal Engine 5.8 Editor session, executing actual editor queries, scene mutations, reflection lookups, and level persistence operations.

---

## 2. Offline Unit Test Coverage (34 Tests Total)

### Summary: 33 Passed, 1 Failed (97.1% Pass Rate)

| Test Module | Tests | Passed | Failed | Execution Time | Coverage Area |
| :--- | :---:| :---:| :---:| :---:| :--- |
| `tests/test_bridge.py` | 8 | 8 | 0 | 0.001s | Streamable HTTP/SSE MCP client protocol handling |
| `tests/test_diagnostics.py` | 6 | 6 | 0 | 0.010s | Engine version, plugin dependencies, process identity |
| `tests/test_live_guards.py` | 3 | 3 | 0 | 0.000s | Transform tolerances, test level naming collisions |
| `tests/test_transport.py` | 6 | 6 | 0 | 3.650s | Ephemeral ThreadingHTTPServer, SSE, redirection, headers |
| `tests/test_install.py` | 4 | 4 | 0 | 0.102s | Plugin installer idempotence, backup generation, INI merge |
| `tests/test_configure.py` | 7 | 6 | 1 | 0.018s | Project configuration, TOML preservation, listener guards |
| **Total** | **34** | **33** | **1** | **3.781s** | |

---

### Detailed Test Inventories

#### A. `tests/test_bridge.py` (8 Tests — 100% Pass)
- `test_accept_loopback`: Asserts `validate_endpoint` accepts `http://127.0.0.1:8000/mcp` and `http://localhost:8000/mcp`.
- `test_reject_nonlocal_urls`: Asserts `validate_endpoint` rejects public IPs, domain names, query strings, and credentials.
- `test_html_not_mcp`: Verifies that receiving an HTML page (e.g. standard web server) raises `MCPError`.
- `test_project_path_normalized`: Validates cross-platform Windows/POSIX path case and separator normalization.
- `test_wrong_project_rejected`: Asserts `verify_project` raises `MCPError` on mismatched `.uproject` paths.
- `test_rpc_error_not_success`: Validates JSON-RPC `error` objects are unpacked as `MCPError`.
- `test_wrong_response_id_rejected`: Validates rejection of JSON-RPC responses with mismatched IDs.
- `test_sse_matching_response`: Asserts SSE stream parser iterates event frames until matching response ID is found.

#### B. `tests/test_diagnostics.py` (6 Tests — 100% Pass)
- `test_status_exit_codes`: Validates exit code translation (0 for PASS, 1 for FAIL, 2 for BLOCKED/NOT TESTED).
- `test_missing_plugin_is_not_compatible`: Verifies engine validation fails when required native plugins are missing.
- `test_wrong_version_rejected`: Verifies engine validation rejects non-5.8 Unreal builds.
- `test_toolset_description_bullets_not_toolsets`: Tests regex parsing of `list_toolsets` output.
- `test_required_argument_and_type_validation`: Tests JSON schema validator against missing or wrongly typed inputs.
- `test_process_identity_rejects_same_name_other_directory`: Validates that an `UnrealEditor.exe` process from another engine build is rejected.

#### C. `tests/test_live_guards.py` (3 Tests — 100% Pass)
- `test_transform_exact_values`: Validates exact transform floating point tolerance assertion.
- `test_first_run_uses_preferred_map`: Asserts test runner picks base test level name when unused.
- `test_existing_map_is_never_reused`: Asserts test runner automatically increments suffix (`_001`, `_002`) to prevent overwriting existing levels.

#### D. `tests/test_transport.py` (6 Tests — 100% Pass)
- `test_real_http_session_headers_and_pagination`: Starts a local `ThreadingHTTPServer` mock and validates JSON-RPC request format, `Mcp-Session-Id` header propagation, and `nextCursor` pagination.
- `test_real_sse_initialization`: Validates initialization over `text/event-stream` SSE response content type.
- `test_closed_server_is_not_operational`: Validates `URLError` handling when target port is closed.
- `test_error_tool_result_is_failure`: Validates MCP `isError: true` tool results raise `MCPError`.
- `test_incorrect_endpoint_returns_transport_error`: Validates HTTP 404 response handling.
- `test_no_redirect_to_remote_server`: Validates that HTTP 302 redirects are refused to prevent SSRF.

#### E. `tests/test_install.py` (4 Tests — 100% Pass)
- `test_project_plugins_backup_and_idempotence`: Verifies installer creates timestamped `.backup-*` files and enables `ModelContextProtocol` and `AllToolsets` idempotently.
- `test_existing_config_and_marketplace_preserved`: Verifies that existing TOML servers and marketplace entries are preserved.
- `test_autostart_updates_existing_section`: Verifies that existing INI sections are updated in place without duplicate section headers.
- `test_mcp_skill_frontmatter`: Verifies YAML frontmatter in `skills/unreal-mcp/SKILL.md`.

#### F. `tests/test_configure.py` (7 Tests — 85.7% Pass, 1 Failure)
- `test_plugins_preserve_other_entries_and_fields`: **PASS**.
- `test_existing_codex_is_byte_preserved`: **PASS**.
- `test_new_registration_preserves_other_servers`: **PASS**.
- `test_duplicates_and_conflicts_are_refused`: **PASS**.
- `test_backup_and_idempotence`: **PASS**.
- `test_ini_preserves_other_sections`: **PASS**.
- `test_public_port_override_rejected_before_configuration`: **FAIL**  
  *Failure Details:* `AttributeError: module 'configure' has no attribute 'guard_listener_overrides'`.  
  *Root Cause:* Function planned and tested in unit suite, but implementation was omitted in `scripts/configure.py`.

---

## 3. Live Integration Test Coverage

Testing executed against running Unreal Editor instance (`UnrealEditor.exe` PID 23088, port 8000):

| Live Suite | Objective | Result | Artifact Generated |
| :--- | :--- | :---:| :--- |
| `scripts/doctor.py` | Full preflight inspection (engine, plugins, config, loopback, MCP handshake, process identity, actor count) | **PASS** (with `codex.cmd` note) | `evidence/doctor.json` |
| `scripts/live_test.py` | End-to-end level duplication, cube spawn, transform assertion, reflection check, save/reload persistence | **PASS** | `evidence/live-test-20261120T190935Z.json` |
| `audit_live_suite.py` | 53 toolsets census, 832 tools deep query, actor Move/Rotate/Scale, duplicate naming, fault injection, Blueprint DSL check | **PASS** | `evidence/audit-live-results.json` |

---

## 4. Live Tool Execution vs Discovery Ratio

```
Total Discovered Native Tools:  832 tools (100.0%)
=====================================================
Directly Exercised Live Tools:   21 tools (  2.5%)
  - Passing Live Executions:     21 tools (100.0% of exercised)
  - Failing Live Executions:      0 tools (  0.0%)
Untested Native Tools:          811 tools ( 97.5%)
```

### Specific Tools Exercised Live:
1. `list_toolsets` (Meta-tool)
2. `describe_toolset` (Meta-tool)
3. `call_tool` (Meta-tool)
4. `SceneTools.get_current_level`
5. `SceneTools.find_actors`
6. `SceneTools.add_to_scene_from_asset`
7. `SceneTools.load_level`
8. `AssetTools.exists`
9. `AssetTools.save_assets`
10. `AssetTools.duplicate`
11. `AssetTools.is_dirty`
12. `ActorTools.get_label`
13. `ActorTools.set_label`
14. `ActorTools.get_actor_transform`
15. `ActorTools.set_actor_transform`
16. `ActorTools.get_components`
17. `ObjectTools.list_properties`
18. `ObjectTools.get_properties`
19. `LogsToolset.GetLogEntries`
20. `EditorAppToolset.IsPIERunning`
21. `BlueprintTools.get_graph_dsl_docs`

---

## 5. Test Isolation & Safety Analysis

- **Production Asset Safety:** All live tests operate exclusively under `/Game/CodexBridgeTests/`. Zero modifications occurred in `/Game/DemoTemplate/`, `/Game/FirstPerson/`, or user assets.
- **Level Overwrite Protection:** Automated guard generates unique timestamped map names (`ARC01_TestLevel_001`, `ARC01_TestLevel_002`, `ARC01_AuditLevel_*`) to eliminate accidental level overwrites.
- **Pre-Save Requirement:** Duplicate map creation in UE 5.8 leaves the newly created map dirty in memory; attempting to call `load_level` on a dirty map causes the engine to refuse the load. The test suite correctly saves the duplicated asset prior to calling `load_level`.
- **Level Restoration:** All test suites safely restore the editor's active level back to the original project map (`/Game/DemoTemplate/_Core/Lvl_IntroRoom`) upon completion.

