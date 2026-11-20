# Set up Unreal MCP and Codex

## Preferred for Unreal Engine 5.9: Codex INSIDE Unreal Editor

1. Edit > Plugins: enable **Unreal Assistant**, **Unreal MCP** (`ModelContextProtocol`), and **All Toolsets**. Restart as prompted.
2. Edit > Editor Preferences > Agentic Workflows > Model Context Protocol: confirm **Auto Start Server** and server endpoint (default `http://127.0.0.1:8000/mcp`).
3. Install Node.js, the Codex CLI and log in (`codex login`). In a Windows PowerShell terminal with Node available, install the ACP adapter: `npm install -g @agentclientprotocol/codex-acp`.
4. Restart Unreal Editor after installing the adapter so its executable is on Unreal's inherited `PATH`.
5. Window > Unreal Assistant. Go to Edit > Editor Preferences > General > Unreal Assistant > External Agent, choose **Codex**, toggle **Use External Agent**, and approve the agent for the project.
6. In the panel, ask: `List available Unreal toolsets and tell me what actors are in the current level.` Once this works, ask for a reversible creation task.

The 5.9 Unreal Assistant panel uses ACP and connects its agent to Unreal MCP itself. This route **does not need** a project `.codex/config.toml` MCP server entry. The skills in this plugin still help with workflows; they may need separate installation in the Codex environment depending on how the ACP adapter loads local plugins.

Official Epic guide: https://dev.epicgames.com/documentation/unreal-engine/run-external-ai-agents-in-the-unreal-assistant-panel-in-unreal-engine

## Alternative for Unreal Engine 5.8+ (or use Codex CLI/IDE/desktop outside the panel)

1. Enable `ModelContextProtocol` (display name Unreal MCP) and `AllToolsets` in the project. Engine builds without these plugins **cannot** use this package alone.
2. Start the MCP server through its editor preferences or the editor console: `ModelContextProtocol.StartServer`. The default URL is `http://127.0.0.1:8000/mcp`.
3. Run the supplied `scripts/install.py` with a path to your `.uproject` to create project-local Codex configuration and install the reusable skills/marketplace. Alternatively, use the Unreal console command `ModelContextProtocol.GenerateClientConfig Codex`; note that existing `.codex/config.toml` files may not be overwritten.
4. Launch Codex with the Unreal project as your current directory, and verify the `unreal-mcp` connection (`/mcp` in Codex CLI, or MCP settings in the desktop client).
5. Ask for a read-only actor query before enabling edits.

## Multiple projects / ports

Give each running editor a unique port, configured in Editor Preferences or launched with `-ModelContextProtocolPort=<port>`. Ensure each Codex project config points at that editor's URL. Never connect to a random port and assume it is the intended game.
