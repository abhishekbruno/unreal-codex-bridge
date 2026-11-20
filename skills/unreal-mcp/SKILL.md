---
name: unreal-mcp
description: Inspect and modify a live Unreal Engine project through its Unreal MCP server. Use for creating or editing levels, actors, Blueprints, widgets, assets, materials, Niagara, Sequencer, animation, gameplay systems, or running editor tests; not for unrelated conceptual questions.
---

# Unreal MCP for Codex

This skill guides Codex when working with Epic's `ModelContextProtocol` and `AllToolsets` Unreal Editor plugins. In Unreal Engine 5.9, Codex may run inside **Window > Unreal Assistant** through ACP; alternatively, a local Codex client can reach `http://127.0.0.1:8000/mcp` through its own MCP configuration.

## Start by establishing reality

1. Confirm `unreal-mcp` is connected. If missing, do not pretend tools ran; follow `references/setup.md`.
2. Discover available toolsets. Versions differ: recent servers may expose `list_toolsets`, `describe_toolsets`, `describe_tools`, and `call_tool`; some prior builds expose `describe_toolset` instead. Inspect actual live schemas rather than assuming a name or parameter.
3. Identify the active Unreal editor project and level, particularly if several editors are open. Ask for the user's intended project only if ambiguous after inspecting tools/metadata.
4. Perform one read-only tool call to validate the editor is live (e.g., actors or selections). A connected proxy or cached catalog alone is insufficient proof.

## Create and edit

- Inspect before changing. Use toolset discovery and descriptions, then invoke actual tools using the exact discovered schemas. Common domains include actor/scene composition, Blueprint graph construction, content assets, UMG widgets, materials, Niagara, Sequencer, PCG, meshes, and automation tests.
- Treat tools as the authority: never claim a Blueprint was compiled, a mesh imported, or a level saved unless the corresponding live call succeeded.
- For multi-step work, establish dependencies and make ordered calls. Do not issue overlapping tool calls against the same editor state; the engine typically executes tool calls on the game thread.
- Use sensible Unreal names and folders (`BP_`, `WBP_`, `M_`, `MI_`, `SM_`, `/Game/...`) while respecting existing project conventions.
- Prefer the engine's native tools. If a capability is not exposed, inspect available toolsets before proposing an extension via `create-toolset`.
- For any bulk/dangerous change, make a recoverable source-control commit or backup first. Ask before deleting or replacing significant existing content. Minimize use of privileged Python execution inside the editor.
- Save changed assets and levels. Compile Blueprints or use Live Coding only when available and safe, then run appropriate tests. Capture tool outputs and describe what succeeded versus what is unverified.

## User-facing response

Summarize created asset paths, important decisions, validation performed, and anything the user still needs to do. A failed tool call is a failure, not a partial success. Do not describe impossible capabilities as available without a live discovery result.

## Setup and recovery

See `references/setup.md` for UE 5.9 panel and external-client setup. See `references/operations.md` for server recovery, toolset discovery, multi-editor ports, and security.
