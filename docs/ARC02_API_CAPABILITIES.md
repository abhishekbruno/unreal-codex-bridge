# Unreal Codex Bridge — ARC 02 API & Toolset Capabilities Reference

**Document Version:** 1.0.0  
**Date:** 2026-11-20  
**Target:** OpenAI Codex & Unreal Engine 5.8.4  
**Observed Toolsets:** 53  
**Observed Tools:** 832  

---

## 1. Discovered Toolset Ecosystem

The Unreal Engine 5.8 native Model Context Protocol (MCP) server exposes 53 distinct toolsets covering every subsystem of the editor:

```
 1. ToolsetRegistry.AgentSkillToolset
 2. AIAssistant.AIAssistantToolset
 3. AutomationTestToolset.AutomationTestToolset
 4. ConfigSettingsToolset.ConfigSettingsToolset
 5. DataRegistryToolset.DataRegistryTools
 6. EditorToolset.EditorAppToolset
 7. EditorToolset.LogsToolset
 8. GameFeaturesToolset.GameFeaturesToolset
 9. GameplayTagsToolset.GameplayTagsToolset
10. GASToolsets.GameplayCueToolset
11. GASToolsets.AttributeSetToolset
12. GASToolsets.AbilitySystemInspectorToolset
13. NiagaraToolsets.NiagaraToolset_Info
14. NiagaraToolsets.NiagaraToolset_Component
15. NiagaraToolsets.NiagaraToolset_Blueprint
16. NiagaraToolsets.NiagaraToolset_System
17. NiagaraToolsets.NiagaraToolset_Assets
18. PluginToolset.PluginToolset
19. SemanticSearchToolset.SemanticSearchToolset
20. DataflowAgent.DataflowAgentToolset
21. PCGToolset.PCGToolset
22. PCGToolset.PCGSpatialToolset
23. SlateInspectorToolset.SlateInspectorToolset
24. PhysicsToolsets.PhysicsAssetToolset
25. WorldConditionsToolset.WorldConditionTools
26. UMGToolSet.UMGToolSet
27. state_tree_toolset.toolsets.state_tree.StateTreeTools
28. editor_toolset.toolsets.actor.ActorTools
29. editor_toolset.toolsets.asset.AssetTools
30. editor_toolset.toolsets.blueprint.BlueprintTools
31. editor_toolset.toolsets.curve_table.CurveTableTools
32. editor_toolset.toolsets.data_asset.DataAssetTools
33. editor_toolset.toolsets.data_table.DataTableTools
34. editor_toolset.toolsets.material.MaterialTools
35. editor_toolset.toolsets.material_instance.MaterialInstanceTools
36. editor_toolset.toolsets.media.MediaTools
37. editor_toolset.toolsets.object.ObjectTools
38. editor_toolset.toolsets.project.ProjectTools
39. editor_toolset.toolsets.scene.SceneTools
40. editor_toolset.toolsets.skeleton.SkeletonTools
41. editor_toolset.toolsets.sound_cue.SoundCueTools
42. editor_toolset.toolsets.static_mesh.StaticMeshTools
43. editor_toolset.toolsets.struct.StructTools
44. editor_toolset.toolsets.subsystem.SubsystemTools
45. editor_toolset.toolsets.texture.TextureTools
46. editor_toolset.toolsets.world_partition.WorldPartitionTools
47. editor_toolset.toolsets.input.InputTools
48. editor_toolset.toolsets.skeletal_mesh.SkeletalMeshTools
49. editor_toolset.toolsets.foliage.FoliageTools
50. editor_toolset.toolsets.landscape.LandscapeTools
51. editor_toolset.toolsets.animation.AnimationTools
52. editor_toolset.toolsets.audio.AudioTools
53. editor_toolset.toolsets.level_sequence.LevelSequenceTools
```

---

## 2. Core Toolset Technical Reference

### 2.1 SceneTools (`editor_toolset.toolsets.scene.SceneTools`)
Provides level inspection, loading, actor queries, and world tracing.

| Tool | Type | Required Inputs | Description |
|:---|:---:|:---|:---|
| `get_current_level` | Read | None | Returns the package path of the currently active level |
| `load_level` | Write | `level_path` (string) | Loads a level map into the active editor context |
| `find_actors` | Read | `name` (str), `tag` (str), `collision_channels` (arr) | Finds actors in current level matching criteria |
| `add_to_scene_from_asset` | Write | `asset_path` (str) | Instantiates an actor from an asset (e.g. StaticMesh) |
| `add_to_scene_from_class` | Write | `class_path` (str) | Instantiates an actor from a UClass path |
| `remove_from_scene` | Write | `actor` (ref) | Deletes an actor from the current level |
| `save_actor` | Write | `actor` (ref) | Marks an actor or dirty level actors as saved |
| `get_collision_channels` | Read | None | Returns available physics collision channel names |
| `trace_world` | Read | `start`, `end`, `channels` | Performs a ray trace query through the world |

### 2.2 ActorTools (`editor_toolset.toolsets.actor.ActorTools`)
Controls transform, labeling, tagging, and component hierarchy on level actors.

| Tool | Type | Required Inputs | Description |
|:---|:---:|:---|:---|
| `get_label` | Read | `actor` (ref) | Returns the outliner display label of the actor |
| `set_label` | Write | `actor` (ref), `label` (str) | Sets the outliner display label of the actor |
| `get_actor_transform` | Read | `actor` (ref) | Returns location (x,y,z), rotation (p,y,r), scale (x,y,z) |
| `set_actor_transform` | Write | `actor` (ref), `transform` (obj) | Sets location, rotation, and scale |
| `get_components` | Read | `actor` (ref) | Returns list of component soft references |
| `add_component` | Write | `actor` (ref), `component_class` (str) | Attaches a new component to the actor |
| `remove_component` | Write | `actor` (ref), `component` (ref) | Detaches and removes a component |
| `get_tags` | Read | `actor` (ref) | Returns array of gameplay/editor tags |
| `add_tag` | Write | `actor` (ref), `tag` (str) | Adds a tag to the actor |
| `remove_tag` | Write | `actor` (ref), `tag` (str) | Removes a tag from the actor |

### 2.3 AssetTools (`editor_toolset.toolsets.asset.AssetTools`)
Manages Content Browser assets, packages, metadata, and dependencies.

| Tool | Type | Required Inputs | Description |
|:---|:---:|:---|:---|
| `find_assets` | Read | `folder_path` (str), `name` (str) | Recursively finds asset packages in a folder |
| `get_asset_class` | Read | `asset_path` (str) | Returns the UClass name of the asset |
| `get_asset_tags` | Read | `asset_path` (str) | Returns asset registry metadata tags dictionary |
| `exists` | Read | `asset_path` (str) | Returns boolean indicating if asset exists |
| `is_dirty` | Read | `asset_path` (str) | Returns boolean indicating if asset has unsaved edits |
| `save_assets` | Write | `asset_paths` (list) | Saves specified assets to disk |
| `duplicate` | Write | `source_path` (str), `destination_path` (str) | Duplicates an asset package |
| `move` | Write | `source_path` (str), `destination_path` (str) | Moves or renames an asset package |
| `delete` | Write | `asset_path` (str) | Deletes an asset package |

### 2.4 ObjectTools (`editor_toolset.toolsets.object.ObjectTools`)
Provides reflection, property inspection, mutation, and class hierarchy queries for any `UObject`.

| Tool | Type | Required Inputs | Description |
|:---|:---:|:---|:---|
| `get_class` | Read | `instance` (ref) | Returns the UClass soft path of the object |
| `list_properties` | Read | `instance` (ref) | Returns list of all serialized property names on object |
| `get_properties` | Read | `instance` (ref), `property_names` (arr) | Reads values of named properties |
| `set_properties` | Write | `instance` (ref), `properties` (obj) | Writes values to named properties |
| `reset_properties`| Write | `instance` (ref), `property_names` (arr) | Resets properties to class defaults |
| `search_subclasses`| Read | `base_class` (str) | Lists all loaded subclasses of a base class |

---

## 3. Blueprint Graph DSL Reference (`BlueprintTools`)

Unreal Engine 5.8 introduces Epic's native **Blueprint Graph Domain Specific Language (DSL)**, an S-expression based declarative representation of Blueprint logic.

### 3.1 Syntax Overview

```lisp
;; Event definition with statements
(event EventName
  stmt ...)

;; Event with parameter bindings
(event EventName (Param1 Param2 ...)
  stmt ...)

;; Function definition
(fn FunctionName
  stmt ...)

;; Function with parameters
(fn FunctionName (Param1 Param2 ...)
  stmt ...)
```

### 3.2 Key Node Constructors

- `(call TargetFunction Arg1 Arg2 ...)`: Invokes a member or static function.
- `(set VariableName Value)`: Assigns a value to a member or local variable.
- `(get VariableName)`: Reads a variable.
- `(branch Condition ThenStmt ElseStmt)`: Conditional control flow.
- `(cast TargetClass Object)`: Dynamic type cast with succeeded/failed branches.
- `(return Value)`: Returns from a function graph.

### 3.3 Available Tools in `BlueprintTools` (53 tools)

- `read_graph_dsl`: Reads an existing Blueprint graph into S-expression DSL text.
- `write_graph_dsl`: Populates a Blueprint graph from DSL text and triggers compilation.
- `get_graph_dsl_docs`: Returns the full formal grammar and usage documentation.
- `list_graphs`: Enumerates graphs (`EventGraph`, `UserConstructionScript`, function graphs).
- `list_variables`: Enumerates member and local variables.
- `list_functions`: Enumerates locally defined and inherited functions.
- `add_variable` / `remove_variable`: Modifies Blueprint variable definitions.
- `add_function_graph` / `remove_function_graph`: Creates and deletes function graphs.
- `create_node` / `delete_node`: Manipulates graph nodes directly.
- `connect_pins` / `break_pins`: Wires execution and data pins.
- `compile_blueprint`: Compiles the Blueprint into executable bytecode.

---

## 4. Safety & Authorization Classification

To prevent unauthorized destruction of user assets, tools are strictly classified:
- **Verified Read-Only:** Queries that cannot mutate assets or scenes. Safe for autonomous discovery and inspection.
- **Conservative Write:** Any tool that modifies properties, changes scene layout, deletes assets, or writes bytecode. Must be executed only during verified task workflows with rollbacks or in dedicated test levels (`/Game/CodexBridgeTests/`).

