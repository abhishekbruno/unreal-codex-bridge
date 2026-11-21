---
name: unreal-game
description: Create, edit, and develop Unreal Engine 5.8 games from natural-language requests in OpenAI Codex. Supports Windows 10/11 and macOS (Apple Silicon & Intel).
---

# Unreal Game Development Workflow

Treat a user prompt to build or modify a game as authorization to implement the gameplay loop in the selected Unreal Engine 5.8 project. This skill operates identically on **Windows** and **macOS**.

## 1. Verify Active Editor and Project Connection

Before mutating any project assets, verify that the Unreal Editor is open and listening to the correct project:

```bash
# Connect and verify the active editor session
python scripts/editor_lifecycle.py status --project "/path/to/Game.uproject"
```

If the editor is not yet running:
```bash
# Check prerequisites and launch the editor
python scripts/editor_lifecycle.py doctor --project "/path/to/Game.uproject"
python scripts/editor_lifecycle.py launch --project "/path/to/Game.uproject"
```

## 2. Retrieve Project Intelligence and Existing Context

Avoid expensive whole-editor rescans by utilizing the persistent SQLite project index:

```bash
# Generate compact project context digest (~1,400 tokens)
python scripts/generate_project_digest.py --db data/project_index.sqlite

# Search for reusable gameplay assets (characters, meshes, sounds)
python scripts/query_project_index.py --search "Character"
python scripts/query_project_index.py --class "StaticMesh"
```

## 3. Plan Gameplay Implementation

Break the request into a playable loop and an observable success condition:
- **Player Input & Pawn:** Movement (WASD/Thumbstick), camera control, jumping.
- **Spawn Point & Level:** Place `PlayerStart` in a safe, grounded location.
- **Objectives & Collectibles:** Actors with trigger collision volumes, pickup counters, and UI bindings.
- **Feedback & UI:** On-screen HUD, score counters, gate animations or visibility toggles.
- **Win / Fail Condition:** Specific observable state triggered upon goal completion.
- **Restart Path:** State reset or level reload without restarting the editor.

## 4. Execute Authorized Asset Mutations

- Always author new content inside the project's `/Game/` directory (e.g. `/Game/Gameplay/`, `/Game/Maps/`).
- Never overwrite or modify engine template assets under `/Engine/`.
- If modifying an existing level, verify the blast radius first:
  ```bash
  python scripts/project_dependencies.py --project "/path/to/Game.uproject" --impact "/Game/Maps/MainLevel"
  ```
- Spawn actors, configure component transforms, and assign meshes using native MCP toolsets (`ActorTools`, `LevelEditorTools`).
- Save touched packages promptly after verification.

## 5. Verify and Playtest

After authoring gameplay:
1. Verify actor properties using `ObjectTools.get_properties`.
2. Compile touched Blueprints or verify Blueprint graphs via `scripts/blueprint_parser.py`.
3. Launch Play-In-Editor using the `unreal-playtest` skill:
   ```bash
   python scripts/playtest.py run --project "/path/to/Game.uproject" --seconds 10
   ```
4. Report observable outcomes: player controls, active level, pickup verification, and playtest logs.
