# Unreal Codex Bridge — ARC 02 Project Intelligence Architecture

**Document Version:** 1.0.0  
**Date:** 2026-11-20  
**Milestone:** ARC 02 Foundation  
**Target:** OpenAI Codex & Unreal Engine 5.8.4  
**Primary Tool:** `scripts/inspect_project.py`  
**Output Artifact:** `reports/project_intelligence.json`  

---

## 1. Overview & Architectural Intent

In ARC 01, Codex established basic communication with Unreal Engine 5.8: creating an actor, modifying its transform, and reloading a map. However, for Codex to act as an autonomous software engineer in Unreal Engine, it cannot operate blindly. It requires **Project Intelligence** — a deep, structured, read-only understanding of:
- What project is open and which Unreal Engine build is running.
- What levels exist and what actors currently populate the active scene.
- Where components, transforms, tags, and properties are organized.
- What assets exist in `/Game` and how they are classified (Blueprints, Materials, StaticMeshes, Textures, etc.).
- How Blueprints are structured: their parent classes, member variables, functions, and event graphs.
- What tools and Graph DSL instructions are available to manipulate them.

`scripts/inspect_project.py` implements this capability. It acts as an autonomous discovery agent that queries the live Unreal Editor session over MCP and produces a structured, bounded intelligence report saved to `reports/project_intelligence.json`.

---

## 2. Safety Guarantees & Non-Destructive Design

The Project Intelligence engine enforces strict read-only safety:
1. **Zero Mutations:** No asset writes (`write_file`), property resets (`reset_properties`), actor deletions (`remove_from_scene`), level modifications (`save_actor`), or graph modifications (`write_graph_dsl`) are ever executed.
2. **Defensive Per-Entity Querying:** Every property lookup (actor label, transform, component list, asset tags, graph list) is wrapped in individual exception guards. If an individual asset or actor has restricted visibility or throws an error, the scan records the error in the schema and continues uninterrupted.
3. **Bounded Query Limits:** To prevent buffer overflow, memory exhaustion, or network timeout on large enterprise projects with 100,000+ assets:
   - `--asset-limit` (default: 100)
   - `--actor-limit` (default: 100)
   - `--blueprint-limit` (default: 25)
4. **Soft Object Path Resolution:** Resolves Unreal soft object paths by mapping `/Game/Path/To/Asset` to `/Game/Path/To/Asset.Asset`, enabling seamless communication with Epic's native `BlueprintTools`.

---

## 3. Intelligence Schema Specification

The generated `reports/project_intelligence.json` adheres to the following top-level schema:

```json
{
  "timestamp_utc": "ISO-8601 UTC timestamp",
  "project": {
    "name": "Project stem name",
    "project_file": "Absolute filesystem path to .uproject",
    "engine_version": "5.8.4",
    "engine_changelist": 58902052,
    "engine_path": "Absolute path to engine root",
    "active_level": "Unreal package path of currently loaded map",
    "listener": {
      "LocalAddress": "127.0.0.1",
      "ProcessId": 23088,
      "ExecutablePath": "Path to UnrealEditor.exe"
    },
    "startup_logs": ["Verified startup log lines"]
  },
  "toolsets": {
    "total_discovered_toolsets": 53,
    "toolset_names": ["List of all 53 advertised toolsets"],
    "cataloged_count": 7,
    "catalog": [
      {
        "name": "Fully qualified toolset name",
        "short_name": "Short identifier",
        "tool_count": 17,
        "tools": [{"name": "tool_name", "description": "tool documentation"}]
      }
    ]
  },
  "scene": {
    "active_level": "/Game/CodexBridgeTests/ARC01_TestLevel_003",
    "total_actors_found": 16,
    "actors_inspected_count": 16,
    "actor_limit_applied": 50,
    "class_distribution": {
      "StaticMeshActor": 3,
      "WorldSettings": 1,
      "Brush": 1,
      "DirectionalLight": 1,
      "SkyAtmosphere": 1
    },
    "actors": [
      {
        "refPath": "Soft object path to actor in persistent level",
        "label": "Human-readable actor label in outliner",
        "class": "Full UClass refPath",
        "transform": {
          "location": {"x": 0.0, "y": 0.0, "z": 150.0},
          "rotation": {"pitch": 0.0, "yaw": 0.0, "roll": 0.0},
          "scale": {"x": 1.0, "y": 1.0, "z": 1.0}
        },
        "component_count": 1,
        "components": [
          {
            "refPath": "Component soft path",
            "class": "Component UClass path"
          }
        ],
        "tags": []
      }
    ]
  },
  "assets": {
    "root_folder": "/Game",
    "total_assets_found": 290,
    "assets_inspected_count": 50,
    "asset_limit_applied": 50,
    "class_distribution": {
      "AnimSequence": 20,
      "Texture2D": 11,
      "InputAction": 4,
      "InputMappingContext": 2,
      "CR_Mannequin_FootIK_C": 1
    },
    "asset_sample": [
      {
        "path": "Unreal package path",
        "name": "Asset name",
        "class": "UClass name",
        "tags_summary": {
          "ParentClass": "Inherited parent class",
          "NativeParentClass": "Native C++ parent class",
          "BlueprintType": "Normal/Interface/Macro/FunctionLibrary",
          "ItemTypeDisplayName": "Human-readable asset type"
        }
      }
    ]
  },
  "blueprints": {
    "toolset_status": {
      "name": "editor_toolset.toolsets.blueprint.BlueprintTools",
      "available": true,
      "tool_count": 53,
      "key_tools": ["read_graph_dsl", "write_graph_dsl", "compile_blueprint"]
    },
    "graph_dsl_available": true,
    "graph_dsl_summary": "Lisp-style S-expression syntax overview",
    "blueprints_found_in_sample": 8,
    "blueprints_inspected_count": 8,
    "blueprint_limit_applied": 15,
    "blueprints": [
      {
        "path": "/Game/FirstPerson/Blueprints/BP_FirstPersonCameraManager",
        "name": "BP_FirstPersonCameraManager",
        "class": "BP_FirstPersonCameraManager_C",
        "parent_class": "/Script/CoreUObject.Class'/Script/Engine.PlayerCameraManager'",
        "native_parent_class": "/Script/CoreUObject.Class'/Script/Engine.PlayerCameraManager'",
        "item_type": "Blueprint Class",
        "graphs": ["UserConstructionScript", "EventGraph"],
        "variables": [],
        "functions": [
          {"name": "UserConstructionScript", "bIsImplemented": true},
          {"name": "PhotographyCameraModify", "bIsImplemented": false},
          {"name": "BlueprintUpdateCamera", "bIsImplemented": false}
        ]
      }
    ]
  },
  "safety_assessment": {
    "read_only_verified": true,
    "mutations_performed": 0,
    "safety_policy": "STRICT_READ_ONLY_INSPECTION"
  }
}
```

---

## 4. Live Verification Results

Executed against the live running editor session (`UnrealCodexTest`, UE 5.8.4 CL 58902052, PID 23088):
- **Discovered Toolsets:** 53 toolsets cataloged.
- **Scene Actors:** 16 actors inspected (`StaticMeshActor`, `WorldSettings`, `Brush`, `DirectionalLight`, `SkyAtmosphere`, etc.).
- **Assets in `/Game`:** 290 assets discovered, 50 sampled across 12 distinct classes.
- **Blueprints Inspected:** 8 Blueprints thoroughly inspected (`CR_Mannequin_FootIK`, `BP_FirstPersonCameraManager`, `BPI_TouchInterface`, `BP_SaveData`, `CtrlRig_FPWarp`, `ABP_FP_Copy`, `UI_InGame`, `ABP_Unarmed`).
- **Graph & Variable Retrieval:** Successfully retrieved graphs (e.g. `AnimGraph`, `EventGraph`, `Locomotion`, `Main States`), member variables (`GroundSpeed`, `Velocity`, `ShouldMove`, `IsFalling`, `Character`, `SpawnPoint`), and function signatures.
- **Output:** Stored at `reports/project_intelligence.json` (74,323 bytes).

