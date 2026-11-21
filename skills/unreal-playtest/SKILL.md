---
name: unreal-playtest
description: Execute, monitor, and evaluate Play-In-Editor (PIE) gameplay sessions in Unreal Engine 5.8 across Windows 10/11 and macOS.
---

# Unreal Play-In-Editor (PIE) Testing Workflow

This skill guides OpenAI Codex through automated and semi-automated Play-In-Editor (PIE) verification of Unreal Engine 5.8 games.

## 1. Pre-Flight Verification

Before launching a playtest session:
1. **Target Map Inspection:** Confirm the active or specified level is loaded and saved.
2. **Compilation Preflight:** Ensure all Blueprints and game code compile without errors or warnings.
3. **Player Start Presence:** Verify that at least one `PlayerStart` actor exists with valid collision bounds.

## 2. Executing a Playtest Session

Use the unified playtest helper script:

```bash
# Start a 10-second playtest session and capture runtime telemetry
python scripts/playtest.py run --project "/path/to/Game.uproject" --duration 10
```

Alternatively, invoke native MCP tools directly:
- `LevelEditorTools.start_pie` (or execute editor console command `Automation Start PIE`)
- Monitor runtime logs from `Saved/Logs/<GameName>.log`
- `LevelEditorTools.stop_pie` (or execute editor console command `Automation Stop PIE`)

## 3. Telemetry and State Observation

During and after the PIE session:
- **Runtime Log Scanning:** Inspect `Saved/Logs/<GameName>.log` for runtime script errors, `Blueprint Runtime Error`, assertion failures, or custom log messages (`LogTemp: Star collected: 1/5`).
- **Property Reflection:** Read back gameplay state (e.g. `Score`, `StarsCollected`, `bGateUnlocked`) from the game state or player pawn.
- **Restart Verification:** Confirm that resetting or reloading the level cleanly restores initial state (`Score == 0`, `bGateUnlocked == false`).

## 4. Reporting Standards & Honesty

- **Do Not Claim False Verification:** Launching PIE alone does not prove gameplay functionality.
- Explicitly distinguish between:
  - **Automated Verification:** Verified via log assertions or reflected gameplay variables.
  - **Manual Verification Required:** Input feel, camera responsiveness, visual styling, or animation blending where automated input simulation is unavailable.
- Report exact log excerpts, duration of playtest, and observed variable states.

