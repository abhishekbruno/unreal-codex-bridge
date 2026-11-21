# Unreal Codex Bridge — ARC 02 Asset Dependency Graph & Impact Analysis

**Document Version:** 1.0.0  
**Date:** 2026-11-21  
**Milestone:** ARC 02 Phase 2  
**Target:** OpenAI Codex & Unreal Engine 5.8.4  
**Primary Module:** `scripts/project_dependencies.py`  
**Test Suite:** `tests/test_dependencies.py` (8 passing unit tests)  

---

## 1. Overview & Problem Definition

In Unreal Engine game development, modifying or deleting an asset without understanding its dependency topology leads to broken references, failed packaging, or runtime crashes. For an AI agent like OpenAI Codex to assist developers safely, it must be able to answer:
- *"Which assets does `BP_FirstPersonCharacter` depend on?"*
- *"If I change or refactor `BP_Player`, which other Blueprints, levels, or materials might be affected?"*
- *"Are there circular references between my skeletal meshes and physics assets?"*
- *"Are any references dangling or pointing to missing assets?"*

The **Asset Dependency Graph Engine** (`scripts/project_dependencies.py`) provides an in-depth, non-destructive graph analysis system using Unreal Engine 5.8's native `AssetTools` APIs (`get_dependencies` and `get_referencers`).

---

## 2. Graph Architecture & Data Model

The graph is modeled as a directed multi-edge graph $G = (V, E)$:
- **Vertices ($V$):** Represent Unreal assets, native engine packages, or script modules.
  - `path`: Normalized package path (e.g. `/Game/FirstPerson/Blueprints/BP_FirstPersonCharacter`).
  - `name`: Short asset name.
  - `class`: UClass name (e.g. `Blueprint`, `Material`, `StaticMesh`, `NativePackage`).
  - `category`: `game_asset` (`/Game/`), `engine_asset` (`/Engine/`), or `native_script` (`/Script/`).
  - `exists`: Boolean indicating whether the asset package is confirmed present.
- **Edges ($E$):** Directed relationships between vertices.
  - **Forward Adjacency (`forward_adj`):** Source depends on Target ($A \rightarrow B$).
  - **Reverse Adjacency (`reverse_adj`):** Target is referenced by Source ($B \leftarrow A$).
  - `edge_type`: `dependency`, `referencer`, `soft_reference`, `hard_reference`.

---

## 3. Graph Traversal & Analysis Algorithms

### 3.1 Transitive Dependencies with Bounded Depth
Traverses forward dependencies using Breadth-First Search (BFS) bounded by a configurable `max_depth` (default: 3 to 5):
$$\text{Deps}(v, d) = \{ u \in V \mid \text{dist}(v, u) \le d \}$$
Returns hierarchical groupings by depth distance, allowing Codex to see immediate dependencies versus distant transitive requirements.

### 3.2 Blast-Radius & Impact Analysis (`get_affected_assets`)
Traverses reverse referencers to calculate the blast radius of modifying an asset:
- **Immediate Referencers (Distance 1):** Assets that directly reference the target. High probability of compilation errors if signatures change.
- **Transitive Referencers (Distance $>1$):** Indirect consumers. Potential ripple effects.
- **Risk Classification:**
  - `HIGH RISK`: $>10$ affected assets.
  - `MEDIUM RISK`: $4–10$ affected assets.
  - `LOW RISK`: $1–3$ affected assets.
  - `NONE`: Isolated leaf asset ($0$ referencers).

> [!IMPORTANT]
> The engine explicitly distinguishes **potential impact** from confirmed breakage. A referencer is flagged as potentially affected because it maintains an asset dependency, but semantic analysis is required to determine whether a specific modification breaks it.

### 3.3 Circular Dependency Detection & Tarjan's SCC Algorithm
- **DFS Cycle Finder (`find_cycles`):** Identifies directed cycle paths ($A \rightarrow B \rightarrow C \rightarrow A$).
- **Tarjan's Strongly Connected Components (`find_strongly_connected_components`):** Groups clusters of mutually reachable nodes with $|SCC| > 1$.

In live testing on `UnrealCodexTest`, the engine detected 3 circular dependencies inherent in standard mannequin assets:
```
Cycle 1: /Game/Characters/Mannequins/Meshes/SKM_Manny_Simple -> /Game/Characters/Mannequins/Rigs/PA_Mannequin -> /Game/Characters/Mannequins/Meshes/SKM_Manny_Simple
Cycle 2: /Game/Characters/Mannequins/Meshes/SK_Mannequin -> /Game/Characters/Mannequins/Meshes/SKM_Manny_Simple -> /Game/Characters/Mannequins/Meshes/SK_Mannequin
Cycle 3: /Game/Characters/Mannequins/Meshes/SK_Mannequin -> /Game/Characters/Mannequins/Meshes/SKM_Quinn_Simple -> /Game/Characters/Mannequins/Meshes/SK_Mannequin
```
This confirms that the graph correctly handles cyclic structures without infinite recursion or stack overflow.

---

## 4. Live Verification Results

Ran live scan against `UnrealCodexTest` (UE 5.8.4, PID 23088):
```powershell
python scripts/project_dependencies.py --asset "/Game/FirstPerson/Blueprints/BP_FirstPersonCharacter" --depth 2 --impact --limit 30
```

### Output Summary
- **Nodes Discovered:** 185 nodes.
- **Edges Discovered:** 303 edges.
- **Cycles Detected:** 3 circular asset loops identified.
- **`BP_FirstPersonCharacter` Direct Dependencies (6):**
  - `/Game/FirstPerson/Anims/ABP_FP_Copy` (Animation Blueprint)
  - `/Game/Input/Actions/IA_Jump` (Input Action)
  - `/Game/Input/Actions/IA_Look` (Input Action)
  - `/Game/Input/Actions/IA_MouseLook` (Input Action)
  - `/Game/Input/Actions/IA_Move` (Input Action)
  - `/Game/Input/Touch/BPI_TouchInterface` (Blueprint Interface)
- **Transitive Dependencies (Depth 2):** 17 total dependencies.
- **Artifact:** Saved to `reports/asset_dependencies.json`.

