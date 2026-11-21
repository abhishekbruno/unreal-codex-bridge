# Installing Unreal Codex Bridge on macOS
## Integration Sprint 01 Guide (Apple Silicon & Intel)

**Target OS:** macOS Sonoma (14.x) / Sequoia (15.x) or higher  
**Hardware Architectures:** Apple Silicon (`arm64`: M1/M2/M3/M4) and Intel (`x86_64`)  
**Target Engine:** Unreal Engine 5.8 (Native Mac build)  
**Target Agent:** OpenAI Codex (Codex CLI / Desktop agent)  

---

## 1. Prerequisites & Architecture Compatibility

1. **Hardware & Architecture Support:**
   - **Apple Silicon (`arm64`):** Supported natively. Unreal Engine 5.8 runs natively on Apple Silicon; Rosetta 2 is not required for plugin operation.
   - **Intel (`x86_64`):** Supported natively on Intel-based Mac hardware.
2. **Unreal Engine 5.8 for Mac:**
   - Standard Epic Games Launcher location: `/Users/Shared/Epic Games/UE_5.8`
   - Verified Editor application bundle:
     `Engine/Binaries/Mac/UnrealEditor.app/Contents/MacOS/UnrealEditor`
3. **Python 3.10+:**
   - Standard Python installed via Homebrew (`brew install python`) or official python.org installer.
4. **OpenAI Codex CLI:**
   - Installed via npm: `npm install -g @openai/codex`
   - Available on PATH as `codex` (e.g. `/opt/homebrew/bin/codex` or `/usr/local/bin/codex`).
   - Authenticated: `codex login`
5. **Developer Tools (Optional / if compiling C++ modules):**
   - Command Line Tools: `xcode-select --install`

---

## 2. Step-by-Step Installation

### Step 1: Clone the Repository
Clone the repository:
```bash
git clone https://github.com/abhishekbruno/unreal-codex-bridge.git
cd unreal-codex-bridge
```

### Step 2: Verify Platform Detection
Run the detection tool:
```bash
python3 scripts/editor_lifecycle.py detect
```
Verify that:
- `platform.is_apple_silicon` correctly reflects your Mac architecture (`true` for M-series, `false` for Intel).
- `architecture` outputs `arm64` or `x86_64`.
- `codex_binary` resolves to the unix executable `/opt/homebrew/bin/codex` or `/usr/local/bin/codex`.
- `installed_engines` lists `/Users/Shared/Epic Games/UE_5.8`.

### Step 3: Prepare Your Unreal Project
Configure project plugins and loopback security:
```bash
python3 scripts/editor_lifecycle.py prepare --project "/path/to/MyGame/MyGame.uproject"
```
This automatically:
- Enables `ModelContextProtocol` and `AllToolsets` in `.uproject`.
- Sets loopback listener security `DefaultBindAddress=127.0.0.1` in `Config/DefaultEngine.ini`.
- Sets auto-start in `Config/DefaultEditorPerProjectUserSettings.ini`.

### Step 4: Register the Codex Plugin
Register the plugin with Codex:
```bash
codex plugin marketplace add .
codex plugin add unreal-codex-bridge@unreal-local
```

### Step 5: Launch the macOS Editor
Launch Unreal Editor with MCP enabled:
```bash
python3 scripts/editor_lifecycle.py launch --project "/path/to/MyGame/MyGame.uproject"
```
*Note on Permissions:* When launching for the first time, macOS may prompt for local network access permissions. Grant permission to allow loopback TCP communication on port 8000.

### Step 6: Verify MCP Handshake & Diagnostics
```bash
python3 scripts/editor_lifecycle.py status --project "/path/to/MyGame/MyGame.uproject"
python3 scripts/editor_lifecycle.py doctor --project "/path/to/MyGame/MyGame.uproject"
```
If errors occur during startup, inspect the macOS editor log:
```bash
cat ~/Library/Logs/Unreal\ Engine/<GameName>Editor/<GameName>.log
```

---

## 3. First Verification: Live Actor Creation
Run the actor creation verification script:
```bash
python3 scripts/live_test.py --project "/path/to/MyGame/MyGame.uproject" --engine "/Users/Shared/Epic Games/UE_5.8"
```
Confirms clean map duplication, actor spawning, transform modification, saving, and reload.
