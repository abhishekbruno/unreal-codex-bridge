# Unreal Editor automation conventions for Codex

When the user asks to modify this Unreal project, use the `unreal-mcp` skill and connected `unreal-mcp` tools to inspect and modify **the running Unreal Editor**. Do not substitute a textual description for an actual tool call.

Before a change: identify the project/level, inspect affected assets, and save or make a backup for bulk edits. Discover toolsets and exact schemas dynamically. Prefer reversible operations and respect project asset naming and folder structure. Ask before overwriting or deleting existing content. Afterward, compile/validate as appropriate, save edited assets/levels, and report exact paths and observed results. Avoid executing arbitrary editor Python when a narrow native tool exists.

If MCP is unavailable, report the specific blocker and refer to the Unreal MCP setup instructions; never say a level or Blueprint was edited when it was not.
