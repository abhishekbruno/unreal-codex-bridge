# ARC 02 Phase 3 research

Inspected local shallow source checkouts on 2026-11-21; no external code installed or copied. All six inspected LICENSE files declare MIT; copying later requires retaining copyright/license notices. Their Unreal integrations also require an appropriately licensed Unreal installation. Node/TypeScript or custom C++ bridge dependencies are not adopted.

## Tractatuz/ue-agent-toolkit

Commit `8cc33939786bf8217830dcd8364ef2389eb85e82`. [Inspected source](https://github.com/Tractatuz/ue-agent-toolkit/blob/8cc33939786bf8217830dcd8364ef2389eb85e82/plugins/ue-agent-toolkit/assets/agents/ue-asset-editor.toml). Native schema-first sequential mutations, explicit save/readback; bounded ralph-loop automation. Custom C++ animation toolsets are unnecessary here.

## qiqt/unreal-mcp

Commit `d1a85396d9c62328521256005fe7c420725651cc`. [Inspected source](https://github.com/qiqt/unreal-mcp/blob/d1a85396d9c62328521256005fe7c420725651cc/mcp-server/src/graphDslCompile.ts). S-expression compiler lowers to its own BuildNode/connections format. Its dialect is not Epic DSL; no reuse of compiler or server.

## CarlxsMG/UEAgent

Commit `4731b2b6aa9d944d4a64dee63f0bbc19b97e53d2`. [Inspected source](https://github.com/CarlxsMG/UEAgent/blob/4731b2b6aa9d944d4a64dee63f0bbc19b97e53d2/Source/UEAgent/Private/Commands/Blueprint/UEAgentBlueprintCommands.cpp). FCompilerResultsLog exposes success/error/warning counts. Graph commands use scoped transactions; global undo is not asset-level recovery.

## WildCake/unreal-engine-mcp-codex

Commit `559ae98e8dd237badde57805c118315e6cbed97f`. [Inspected source](https://github.com/WildCake/unreal-engine-mcp-codex/blob/559ae98e8dd237badde57805c118315e6cbed97f/skills/unreal-engine-mcp-codex/scripts/check_unreal_mcp.py). Setup probes treat HTTPError as reachability. Use actual MCP handshake and project identity, not HTTP reachability, as acceptance.

## FunplayAI/funplay-unreal-mcp

Commit `688c21fe7ea0be7c1f698f058161fef2cc659086`. [Inspected source](https://github.com/FunplayAI/funplay-unreal-mcp/blob/688c21fe7ea0be7c1f698f058161fef2cc659086/FunplayMCP/Content/Python/funplay_mcp/tools/blueprints.py). Blueprint factory creation immediately saves; compile wrapper reports success without explicit returned status. Reject premature save and exception-only verification.

## db-lyon/ue-mcp

Commit `5c6643060ed65ac75dc85afb5efebc1d089cb7d8`. [Inspected source](https://github.com/db-lyon/ue-mcp/blob/5c6643060ed65ac75dc85afb5efebc1d089cb7d8/src/checkpoints/service.ts). Pre-save package checkpoints/shadow repository are stronger than DSL snapshots. Asset tools save by default; require explicit delayed save. Existing-asset edits remain disabled until recoverable checkpoints exist.

## Decisions

Preserve native MCP, standard-library Python client, SQLite indexing, dependencies and existing parser. Add a strict bounded declarative subset, deterministic Epic DSL, semantic graph readback, exclusive process locks and durable journals. No raw DSL or executable code accepted in JSON. No automatic undo/delete on failure. New failed assets remain identifiable for manual recovery.

Engine evidence: UE 5.8.4 blueprint_dsl.py defines the actual dialect; toolset_registry/helpers.py checks Blueprint Status inside compilation, but exposes no status payload. ObjectTools.get_properties redirects Blueprint objects to their CDO, so it cannot read Blueprint Status. The 53-toolset live catalog has no reload operation. These gaps must not be disguised as verified persistence or explicit compiler diagnostics.
