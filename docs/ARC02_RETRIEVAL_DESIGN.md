# Unreal Codex Bridge — ARC 02 Context Retrieval & Search Design

**Document Version:** 1.0.0  
**Date:** 2026-11-21  
**Milestone:** ARC 02 Phase 2  
**Target:** OpenAI Codex & Unreal Engine 5.8.4  
**Primary Module:** `scripts/query_project_index.py`  
**Test Suite:** `tests/test_query_index.py` (9 passing unit tests)  

---

## 1. Overview & Retrieval Philosophy

When an AI coding assistant performs tasks in an Unreal project, feeding the entire project structure into the model prompt causes context window saturation and hallucinations. 

Instead of relying on heavy vector embeddings or ungrounded semantic search, the **Context Retrieval Engine** (`scripts/query_project_index.py`) implements deterministic, indexed retrieval powered by SQLite and FTS5.

### Principles:
1. **Deterministic Ranking:** Prioritize exact, authoritative metadata matches before fuzzy text.
2. **Confidence Attribution:** Every search result provides an explicit confidence rating ($0.70$ to $1.00$) and match rationale (`exact_path`, `exact_name`, `blueprint_member_match`, `fts_match`).
3. **Structured Relationship Embedding:** Whenever an asset is retrieved, its immediate dependency and referencer topology is included automatically.
4. **Token-Budgeted Context Delivery:** Delivers concise Markdown summaries or raw structured JSON tailored to Codex prompt specifications.

---

## 2. Multi-Stage Ranking Pipeline

When a developer or agent issues a query (e.g. `python scripts/query_project_index.py -q "PlayerHealth"`):

```
+-------------------------------------------------------------+
|                      User / Agent Query                     |
+-------------------------------------------------------------+
                              |
                              v
   +-------------------------------------------------------+
   | Stage 1: Exact Package Path Match                     | -> Confidence: 1.00
   | (e.g. /Game/FirstPerson/Blueprints/BP_Player)         |
   +--------------------------+----------------------------+
                              | (If not resolved or more requested)
                              v
   +-------------------------------------------------------+
   | Stage 2: Exact Asset Name Match                       | -> Confidence: 0.95
   | (e.g. name = 'BP_Player')                             |
   +--------------------------+----------------------------+
                              |
                              v
   +-------------------------------------------------------+
   | Stage 3: Blueprint Member Match (Variable / Function) | -> Confidence: 0.90
   | (e.g. variable = 'PlayerHealth' in BP_Player)         |
   +--------------------------+----------------------------+
                              |
                              v
   +-------------------------------------------------------+
   | Stage 4: Substring / Prefix Match on Asset Name/Class | -> Confidence: 0.80
   | (e.g. name LIKE '%Player%')                           |
   +--------------------------+----------------------------+
                              |
                              v
   +-------------------------------------------------------+
   | Stage 5: Full-Text Search (SQLite FTS5 Porter Stemmer) | -> Confidence: 0.70
   | (e.g. fts_index MATCH 'health*')                      |
   +-------------------------------------------------------+
```

---

## 3. Query Capabilities & Supported Filters

| CLI Flag | Function | Target Table | Example Query |
|:---|:---|:---|:---|
| `--path` | Exact package path lookup | `assets` | `--path /Game/DemoTemplate/_Core/EditorUI/UI_InGame` |
| `--name` | Asset name search (exact / prefix) | `assets` | `--name BP_FirstPersonCharacter` |
| `--type` | Class/type filter | `assets` | `--type Material` |
| `--variable` | Find Blueprints defining variable | `blueprints` | `--variable SpawnPoint` |
| `--function` | Find Blueprints defining function | `blueprints` | `--function ToggleDetails` |
| `--actor` | Find level actors by label/class | `actors` | `--actor DirectionalLight` |
| `-q`, `--query` | Multi-tier deterministic search | Hybrid / FTS5 | `-q "SaveData"` |
| `--json` | Return structured JSON output | All | Outputs JSON schema for LLM tool call ingestion |

---

## 4. Output Schema & Example Response

Querying `python scripts/query_project_index.py --variable SpawnPoint --json`:

```json
[
  {
    "matched_path": "/Game/DemoTemplate/_Core/BP_SaveData",
    "asset_type": "Blueprint",
    "match_reason": "blueprint_variable_match: SpawnPoint",
    "confidence": 0.9,
    "source": "sqlite_index",
    "freshness": "active",
    "record": {
      "asset_path": "/Game/DemoTemplate/_Core/BP_SaveData",
      "name": "BP_SaveData",
      "parent_class": "/Script/CoreUObject.Class'/Script/Engine.SaveGame'",
      "native_parent": "/Script/CoreUObject.Class'/Script/Engine.SaveGame'",
      "item_type": "Blueprint Class",
      "graph_count": 1,
      "variable_count": 1,
      "function_count": 0,
      "graphs": ["EventGraph"],
      "variables": ["SpawnPoint"],
      "functions": [],
      "dsl_summary": "",
      "relationships": {
        "dependencies": [],
        "referencers": ["/Game/DemoTemplate/_Core/BP_GM_Template"]
      }
    }
  }
]
```

This response immediately tells Codex:
1. `BP_SaveData` is the exact Blueprint defining `SpawnPoint`.
2. It inherits from `SaveGame`.
3. It has 1 graph (`EventGraph`).
4. It is referenced by `BP_GM_Template` (GameMode).
No further queries or file reads are needed for Codex to reason about this asset.

