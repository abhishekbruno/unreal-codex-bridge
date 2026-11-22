# Five-Star Collection Game Benchmark
## Cross-Platform Gameplay Acceptance Specification

**Benchmark ID:** `bench-game-five-star-v1`  
**Target Engines:** Unreal Engine 5.8.4 (Windows) / Unreal Engine 5.8.x (macOS Apple Silicon & Intel)  
**Agent:** OpenAI Codex  

---

## 1. Overview & Objective

The **Five-Star Collection Game Benchmark** establishes an objective, platform-agnostic gameplay verification criteria for agent-driven Unreal game development.

The AI agent is given the natural-language prompt:
> *"Build a small Unreal game in this project. Let me move with WASD/controller, collect five stars to open a gate, show my score, provide completion feedback, and let me restart the game with state reset. Playtest it before and after the fifth pickup."*

---

## 2. Core Gameplay Requirements

| Requirement ID | Name | Description | Verification Method |
| :--- | :--- | :--- | :--- |
| **REQ-MOVE** | Character Movement | Player character moves in 3D space with collision enabled via standard WASD/thumbstick axes. | Telemetry / PIE Input |
| **REQ-STAR** | 5 Collectible Stars | Exactly 5 distinct collectible actors placed in the map with collision triggers. | Scene Outliner / Asset Count |
| **REQ-SCORE** | Score Tracking | On overlap, each star increments the player's score counter (`Score = 1..5`) and disappears. | GameState / Log Telemetry |
| **REQ-GATE** | Gate Unlock Mechanic | A barrier/gate actor remains closed for 0–4 pickups, and transitions to open/unlocked upon pickup #5. | Actor Property / Transform Check |
| **REQ-FEED** | Completion Feedback | Audio cue, visual message, or particle effect triggered when the 5th star is gathered. | HUD / Screen Message Log |
| **REQ-REST** | Game Restart & Reset | Restarting (via key press or level reload) restores score to 0, respawns all 5 stars, and closes the gate. | State Readback after reload |

---

## 3. Automated Test Harness

The benchmark acceptance criteria are evaluated using `scripts/playtest.py` and the criteria defined in `acceptance.json`:

```bash
# Run acceptance evaluation on target level
python scripts/playtest.py run --project "/path/to/Game.uproject" --duration 15
```

---

## 4. Platform Verification Matrix

| Test Criterion | Windows 10/11 (x86_64) | macOS (Apple Silicon arm64) | macOS (Intel x86_64) |
| :--- | :--- | :--- | :--- |
| **Harness Specification** | **PASS** | **PASS** | **PASS** |
| **Offline Schema Validation** | **PASS** | **PASS** | **PASS** |
| **Asset Creation Verification** | **PASS** (Live Tested) | **BLOCKED** (No Mac hardware) | **BLOCKED** (No Mac hardware) |
| **PIE Session Execution** | **PASS** (Live Tested) | **BLOCKED** (No Mac hardware) | **BLOCKED** (No Mac hardware) |
| **Gameplay State Readback** | **PASS** (Live Tested) | **NOT TESTED** | **NOT TESTED** |

*(Note: Physical macOS verification is marked BLOCKED where host hardware is unavailable; specifications and test logic remain 100% cross-platform).*

