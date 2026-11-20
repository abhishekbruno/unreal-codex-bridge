# Unreal MCP operations and recovery

Useful Unreal console commands: `ModelContextProtocol.StartServer [port]`, `ModelContextProtocol.StopServer`, `ModelContextProtocol.RefreshTools`, and `ModelContextProtocol.GenerateClientConfig Codex`.

If tools aren't available: ensure the editor is running, enable Unreal MCP and All Toolsets, check the Output Log, confirm the configured local port, and restart the editor after enabling new plugins. A server without All Toolsets can respond but offer no useful editor actions.

Discovery APIs differ by engine build. Confirm the server's actual advertised MCP tools; tool-search mode commonly exposes toolset listing, descriptions, schemas, and a dispatcher called `call_tool`. Never guess parameters. For UE 5.9, `describe_toolsets` and `describe_tools` may be separate meta-tools, unlike earlier versions using `describe_toolset`.

If an optional MCP proxy is configured, a live connection to the proxy does not guarantee the editor is running. Verify with a read-only actor tool. After recovery, restart/reconnect the Codex MCP client if it has stale catalogs.

The native Unreal MCP server is unauthenticated and intended for local development. Keep it loopback-only. Do not expose port 8000 through a public tunnel, port-forward, or reverse proxy without a strong authentication and authorization layer. Scripts executed through privileged editor toolsets may alter assets and the filesystem. Save or commit before major edits, and inspect changes afterward.

For Unreal Engine 5.9, official documentation: https://dev.epicgames.com/documentation/unreal-engine/unreal-mcp-in-unreal-editor
