# Unreal Codex Bridge — Troubleshooting & Diagnostics Guide
## Cross-Platform Common Issues & Resolutions

---

## 1. Port 8000 Collision or Multiple Editors Running

### Symptom:
`ConnectionError: Port 8000 is already in use. Please specify a free port or inspect the active editor.`

### Cause:
Another Unreal Editor instance, background daemon, or local service is listening on port 8000.

### Resolution:
1. Inspect the listening process:
   ```bash
   python scripts/editor_lifecycle.py status --port 8000
   ```
2. If running multiple projects simultaneously, assign an offset port (e.g. 8100) to the second project:
   ```bash
   python scripts/editor_lifecycle.py prepare --project "/path/to/SecondProject.uproject" --port 8100
   python scripts/editor_lifecycle.py launch --project "/path/to/SecondProject.uproject" --port 8100
   ```

---

## 2. Listener Security Guard Violation

### Symptom:
`ValueError: Unsafe DefaultBindAddress in ListenerOverrides section: 0.0.0.0` or `Unsafe public/non-loopback ListenerOverrides`

### Cause:
`Config/DefaultEngine.ini` contains wildcard (`0.0.0.0`, `::`) or public network bindings under `[HTTPServer.Listeners]`. Epic's MCP server does not implement authentication; binding it to non-loopback addresses exposes the editor to remote arbitrary code execution.

### Resolution:
1. Inspect `Config/DefaultEngine.ini`.
2. Ensure the bind address is strictly loopback:
   ```ini
   [HTTPServer.Listeners]
   DefaultBindAddress=127.0.0.1
   ```
3. Re-run `python scripts/editor_lifecycle.py prepare --project "<path>"`.

---

## 3. Codex CLI Not Found

### Symptom:
`doctor` reports `BLOCKED: codex_cli: Codex CLI absent from PATH`

### Cause:
On Windows, npm global CLIs are installed as `codex.cmd` in `%APPDATA%\npm`, which may not be present in the calling shell's PATH. On macOS, `codex` is typically in `/opt/homebrew/bin` or `/usr/local/bin`.

### Resolution:
- **Windows:**
  Ensure Node.js and npm global directories are on your PATH:
  ```powershell
  $env:PATH += ";$env:APPDATA\npm"
  npm install -g @openai/codex
  codex --version
  ```
- **macOS:**
  Ensure Homebrew bin is in your shell profile (`~/.zshrc`):
  ```bash
  export PATH="/opt/homebrew/bin:$PATH"
  npm install -g @openai/codex
  codex --version
  ```

---

## 4. macOS Application Bundle or Security Prompts

### Symptom:
macOS dialog: *"UnrealEditor would like to find and connect to devices on your local network"* or Gatekeeper prompts.

### Cause:
macOS Sandboxing and Privacy controls regulate local socket creation.

### Resolution:
1. Click **Allow** on the local network prompt. This authorizes loopback communication on `127.0.0.1`.
2. Do **not** disable Gatekeeper or modify code signing.
3. If editor fails to open, inspect the macOS crash/startup log:
   ```bash
   cat ~/Library/Logs/Unreal\ Engine/<GameName>Editor/<GameName>.log
   ```

---

## 5. Game Descriptor Missing Required Plugins

### Symptom:
`ValueError: ModelContextProtocol is not enabled` or `AllToolsets is not enabled`

### Cause:
The `.uproject` file has not declared the native experimental MCP plugins.

### Resolution:
Run the prepare subcommand to add them automatically:
```bash
python scripts/editor_lifecycle.py prepare --project "/path/to/Game.uproject"
```

---

## 6. Long-Running Tool Timeouts

### Symptom:
`mcp.client.TimeoutError: Operation timed out after 45s` during asset cooking or level loading.

### Cause:
Complex editor operations run synchronously on Unreal's main game thread.

### Resolution:
In `.mcp.json`, the tool timeout is set to 180 seconds by default. When calling scripts via CLI, pass `--timeout 180`:
```bash
python scripts/editor_lifecycle.py connect --timeout 180
```

