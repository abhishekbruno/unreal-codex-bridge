# Unreal Engine Project Context Digest: `UnrealCodexTest`

**Generated:** 2026-11-20 19:56:01 UTC  
**Target Engine:** Unreal Engine 5.8 (Build Path: `D:\UE_5.8`)  
**Project File:** `D:\newpproject\UnrealCodexTest\UnrealCodexTest.uproject`  
**Active Loaded Level:** `/Game/CodexBridgeTests/ARC01_TestLevel_003`  
**Index Freshness:** Last scanned `2026-11-20T19:54:37.371487+00:00` (Source: SQLite FTS5 Persistent Cache)

## 1. Asset Inventory Overview

- **Total Indexed Assets:** 69 (60 active, 9 stale)
| Asset Class | Count | Percentage |
| :--- | :---: | :---: |
| `AnimSequence` | 20 | 29.0% |
| `Texture2D` | 20 | 29.0% |
| `InputAction` | 4 | 5.8% |
| `MaterialInstanceConstant` | 4 | 5.8% |
| `InputMappingContext` | 2 | 2.9% |
| `Material` | 2 | 2.9% |
| `SkeletalMesh` | 2 | 2.9% |
| `ABP_FP_Copy_C` | 1 | 1.4% |

## 2. Core Blueprint Systems & Gameplay Architecture

| Blueprint Name | Parent Class | Graphs | Variables | Functions | DSL Summary |
| :--- | :--- | :---: | :---: | :---: | :--- |
| `UI_Thumbstick` | `UserWidget` | 3 | 9 | 25 | Graph containing 2 events, 0 function... |
| `UI_TouchSimple` | `UserWidget` | 1 | 1 | 24 | Graph containing 5 events, 0 function... |
| `UI_InGame` | `UserWidget` | 1 | 0 | 24 | Graph containing 4 events, 0 function... |
| `BPI_TouchInterface` | `Interface` | 4 | 0 | 4 | Standard graph |
| `BP_FirstPersonCameraManager` | `PlayerCameraManager` | 2 | 0 | 3 | Standard graph |
| `ABP_Unarmed` | `AnimInstance` | 18 | 7 | 2 | Graph containing 2 events, 0 function... |
| `ABP_FP_Copy` | `AnimInstance` | 2 | 0 | 2 | Graph containing 1 events, 0 function... |
| `CR_Mannequin_FootIK` | `ControlRig` | 2 | 6 | 1 | Standard graph |
| `BP_FirstPersonPlayerController` | `PlayerController` | 2 | 1 | 1 | Graph containing 1 events, 0 function... |
| `BP_SaveData` | `SaveGame` | 1 | 1 | 0 | Standard graph |

## 3. Key Blueprint APIs & State Definitions

### `UI_Thumbstick` (`/Game/Input/Touch/UI_Thumbstick`)
- **Graphs:** UI_Thumbstick:Touch Input Check, UI_Thumbstick:EventGraph, UI_Thumbstick:Stick Input
- **Variables:** `[TrackInput, Initial Touch Location, Position, Stick Input, Thumbstick Size, Invert X, Invert Y, Scale Output]`
- **Functions:** `[Touch Input Check, OnTouchStarted, OnTouchMoved, OnTouchGesture, OnTouchForceChanged, OnTouchFirstMove, OnTouchEnded, OnPreviewMouseButtonDown]`
- **Logic Summary:** Graph containing 2 events, 0 functions, 42 calls (Cyclomatic Complexity: 3)

### `UI_TouchSimple` (`/Game/Input/Touch/UI_TouchSimple`)
- **Graphs:** UI_TouchSimple:EventGraph
- **Variables:** `[In String]`
- **Functions:** `[OnTouchStarted, OnTouchMoved, OnTouchGesture, OnTouchForceChanged, OnTouchFirstMove, OnTouchEnded, OnPreviewMouseButtonDown, OnPreviewKeyDown]`
- **Logic Summary:** Graph containing 5 events, 0 functions, 14 calls (Cyclomatic Complexity: 1)

### `UI_InGame` (`/Game/DemoTemplate/_Core/EditorUI/UI_InGame`)
- **Graphs:** UI_InGame:EventGraph
- **Functions:** `[OnTouchStarted, OnTouchMoved, OnTouchGesture, OnTouchForceChanged, OnTouchFirstMove, OnTouchEnded, OnPreviewMouseButtonDown, OnPreviewKeyDown]`
- **Logic Summary:** Graph containing 4 events, 0 functions, 26 calls (Cyclomatic Complexity: 5)

### `BPI_TouchInterface` (`/Game/Input/Touch/BPI_TouchInterface`)
- **Graphs:** BPI_TouchInterface:Primary Thumbstick, BPI_TouchInterface:Secondary Thumbstick, BPI_TouchInterface:Touch Jump Start, BPI_TouchInterface:Touch Jump End
- **Functions:** `[Primary Thumbstick, Secondary Thumbstick, Touch Jump Start, Touch Jump End]`

### `BP_FirstPersonCameraManager` (`/Game/FirstPerson/Blueprints/BP_FirstPersonCameraManager`)
- **Graphs:** BP_FirstPersonCameraManager:UserConstructionScript, BP_FirstPersonCameraManager:EventGraph
- **Functions:** `[UserConstructionScript, PhotographyCameraModify, BlueprintUpdateCamera]`

## 4. Critical Dependency Hubs (High Blast Radius)

Assets referenced by the most other assets. Modifying these requires regression testing:

| Asset Package Path | Direct Referencers | Risk Assessment |
| :--- | :---: | :--- |
| `/Game/Characters/Mannequins/Meshes/SK_Mannequin` | 136 | **HIGH RISK** |
| `/Game/Characters/Mannequins/Meshes/SKM_Quinn_Simple` | 54 | **HIGH RISK** |
| `/Game/DemoTemplate/_Core/DevCom/DL_DevCom` | 22 | **HIGH RISK** |
| `/Game/Characters/Mannequins/Meshes/SKM_Manny_Simple` | 11 | **HIGH RISK** |
| `/Game/Characters/Mannequins/Textures/Shared/T_UE_Logo_M` | 6 | **HIGH RISK** |
| `/Game/Characters/Mannequins/Anims/Unarmed/MM_Idle` | 5 | **HIGH RISK** |

## 5. Active Scene Outliner Summary (`/Game/CodexBridgeTests/ARC01_TestLevel_003`)

| Actor Class | Count | Example Labels in World |
| :--- | :---: | :--- |
| `StaticMeshActor` | 3 | SM_SkySphere, Floor, Codex_Test_Cube |
| `WorldSettings` | 1 | WorldSettings1 |
| `VolumetricCloud` | 1 | VolumetricCloud |
| `SkyLight` | 1 | SkyLight |
| `SkyAtmosphere` | 1 | SkyAtmosphere |
| `PlayerStart` | 1 | PlayerStart |
| `GameplayDebuggerPlayerManager` | 1 | GameplayDebuggerPlayerManager0 |
| `ExponentialHeightFog` | 1 | ExponentialHeightFog |

## 6. Index Quality & Coverage Indicators

- **Active Records:** 60 / 69 (87.0%)  
- **Stale Records:** 9  
- **Indexing Safety:** STRICT_READ_ONLY (0 mutations executed)  

## 7. Recommended Next Inspection Targets

For gameplay and character modifications, inspect in order:
1. Player character controller: `/Game/FirstPerson/Blueprints/BP_FirstPersonCharacter`
2. Animation controller: `/Game/Characters/Mannequins/Anims/Unarmed/ABP_Unarmed`
3. Game mode rules: `/Game/FirstPerson/Blueprints/BP_FirstPersonGameMode`
4. Core UI controller: `/Game/DemoTemplate/_Core/EditorUI/UI_InGame`
