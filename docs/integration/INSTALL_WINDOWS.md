# Installing Unreal Codex Bridge on Windows 10/11
## Integration Sprint 01 Guide

**Target OS:** Windows 10 / 11 (64-bit AMD64 / x86_64 or ARM64)  
**Target Engine:** Unreal Engine 5.8 (Verified baseline: UE 5.8.4 CL 58902052)  
**Target Agent:** OpenAI Codex (Codex CLI / Desktop agent)  

---

## 1. Prerequisites

Before installing the plugin, ensure the following components are installed:

1. **Unreal Engine 5.8:**
   - Installed via Epic Games Launcher (e.g. `C:\Program Files\Epic Games\UE_5.8` or custom drive `D:\UE_5.8`).
   - Required native experimental plugins included with the engine:
     - `ModelContextProtocol`
     - `AllToolsets`
     - `ToolsetRegistry`
2. **Python 3.10+:**
   - Standard Python 3.10, 3.11, or 3.12 (standard library only; no external package dependencies required).
3. **OpenAI Codex CLI:**
   - Installed via npm: `npm install -g @openai/codex`
   - Authenticated: `codex login`

---

## 2. Step-by-Step Installation

### Step 1: Clone the Repository
Clone the repository to your local development machine:
```powershell
git clone https://github.com/abhishekbruno/unreal-codex-bridge.git
cd unreal-codex-bridge
```

### Step 2: Verify System Detection
Run the platform detection preflight:
```powershell
python scripts/editor_lifecycle.py detect
```
Verify that:
- `architecture` reports `x86_64` or `arm64`.
- `codex_binary` resolves to `codex.cmd` or `codex.exe`.
- `installed_engines` lists your Unreal Engine 5.8 directory.

### Step 3: Prepare Your Unreal Project
Configure your target `.uproject` and editor INI files automatically with timestamped backups:
```powershell
python scripts/editor_lifecycle.py prepare --project "D:\Projects\MyGame\MyGame.uproject"
```
This automatically:
- Enables `ModelContextProtocol` and `AllToolsets` for the `Editor` target in `.uproject`.
- Binds listener security to `127.0.0.1` in `Config/DefaultEngine.ini`.
- Enables auto-start on port 8000 in `Config/DefaultEditorPerProjectUserSettings.ini`.

### Step 4: Register the Codex Plugin
Register the local marketplace catalog and enable the plugin:
```powershell
codex plugin marketplace add .
codex plugin add unreal-codex-bridge@unreal-local
```

### Step 5: Launch the Unreal Editor
Launch the project with MCP server auto-start enabled:
```powershell
python scripts/editor_lifecycle.py launch --project "D:\Projects\MyGame\MyGame.uproject"
```

### Step 6: Verify MCP Handshake & Diagnostics
Once the editor finishes loading assets, run diagnostics:
```powershell
python scripts/editor_lifecycle.py status --project "D:\Projects\MyGame\MyGame.uproject"
python scripts/editor_lifecycle.py doctor --project "D:\Projects\MyGame\MyGame.uproject"
```
Ensure all checks return `PASS`.

---

## 3. First Verification: Live Actor Creation
Run the end-to-end verification script to create, transform, save, and reload a test actor in an isolated map:
```powershell
python scripts/live_test.py --project "D:\Projects\MyGame\MyGame.uproject" --engine "D:\UE_5.8"
```
You should see:
- Isolated test map created (`ARC01_TestLevel_...`).
- Actor `Codex_Test_Cube` spawned at `(0, 0, 150)`.
- Level saved and reloaded with transform verified.
- Status: `PASS`.

