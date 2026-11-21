# Unreal Codex Bridge — ARC 02 Persistent Project Indexing (SQLite + FTS5)

**Document Version:** 1.0.0  
**Date:** 2026-11-21  
**Milestone:** ARC 02 Phase 2  
**Target:** OpenAI Codex & Unreal Engine 5.8.4  
**Primary Module:** `scripts/project_index.py`  
**Database Location:** `data/project_index.sqlite` (Kept out of Git)  
**Test Suite:** `tests/test_project_index.py` (7 passing unit tests)  

---

## 1. Architectural Intent & Problem Statement

Full project scans across large Unreal Engine projects (tens of thousands of assets) over MCP HTTP/SSE transport create unacceptable latency (tens of seconds) and excessive token overhead if performed on every AI reasoning turn.

The **Persistent Project Index Engine** (`scripts/project_index.py`) resolves this by establishing a lightweight, queryable, embedded SQLite database utilizing SQLite 3.49+ and the FTS5 full-text search engine.

Key architectural properties:
- **Zero Third-Party Dependencies:** Relies purely on Python's standard library `sqlite3`.
- **Deterministic IDs:** Uses deterministic SHA-256 hashes of normalized Unreal package paths.
- **Transactional & Interruption-Safe:** Uses ACID transactions per entity batch.
- **Schema Versioned:** Tracks schema migrations via the `meta` table (current version: `1`).
- **Incremental Change Detection:** Leverages disk modification timestamps (`mtime`) on local `.uasset` and `.umap` files in `Content/` to skip querying unchanged assets.
- **Strictly Read-Only:** Never modifies, checks out, or writes to project assets or configuration.

---

## 2. Database Schema Specification

```sql
-- Schema Version & Engine Identity Metadata
CREATE TABLE meta (
    key TEXT PRIMARY KEY,
    value TEXT,
    updated_at TEXT
);

-- Core Asset Catalog
CREATE TABLE assets (
    id TEXT PRIMARY KEY,               -- Deterministic SHA-256 hash (first 16 chars)
    path TEXT UNIQUE,                  -- Normalized package path (/Game/...)
    name TEXT,                         -- Asset name
    class TEXT,                        -- UClass identifier
    package_folder TEXT,               -- Package directory (/Game/Folder)
    is_blueprint INTEGER DEFAULT 0,    -- 1 if Blueprint asset, else 0
    parent_class TEXT,                 -- Inherited parent class
    native_parent TEXT,                -- Native C++ parent class
    item_type TEXT,                    -- Human-readable asset type
    metadata_json TEXT,                -- Serialized metadata tags dictionary
    mtime REAL DEFAULT 0,              -- Disk modification timestamp
    status TEXT DEFAULT 'active',      -- 'active', 'stale', or 'missing'
    updated_at TEXT
);
CREATE INDEX idx_assets_name ON assets(name);
CREATE INDEX idx_assets_class ON assets(class);
CREATE INDEX idx_assets_folder ON assets(package_folder);

-- Deep Blueprint Introspection Catalog
CREATE TABLE blueprints (
    asset_path TEXT PRIMARY KEY,
    name TEXT,
    parent_class TEXT,
    native_parent TEXT,
    item_type TEXT,
    graph_count INTEGER DEFAULT 0,
    variable_count INTEGER DEFAULT 0,
    function_count INTEGER DEFAULT 0,
    graphs_json TEXT,                  -- Array of graph names
    variables_json TEXT,               -- Array of member variable definitions
    functions_json TEXT,               -- Array of function signatures
    dsl_summary TEXT,                  -- AST summary of logic graphs
    updated_at TEXT,
    FOREIGN KEY (asset_path) REFERENCES assets(path) ON DELETE CASCADE
);

-- Scene Actors in Active Level
CREATE TABLE actors (
    id TEXT PRIMARY KEY,
    level_path TEXT,
    ref_path TEXT UNIQUE,              -- Soft path in persistent level
    label TEXT,                        -- Outliner label
    class TEXT,                        -- UClass name
    location_x REAL, location_y REAL, location_z REAL,
    rotation_p REAL, rotation_y REAL, rotation_r REAL,
    scale_x REAL, scale_y REAL, scale_z REAL,
    component_count INTEGER DEFAULT 0,
    components_json TEXT,              -- Array of component references & types
    tags_json TEXT,                    -- Array of gameplay/editor tags
    updated_at TEXT
);
CREATE INDEX idx_actors_level ON actors(level_path);
CREATE INDEX idx_actors_label ON actors(label);
CREATE INDEX idx_actors_class ON actors(class);

-- Forward & Reverse Asset Dependencies
CREATE TABLE dependencies (
    source_path TEXT,
    target_path TEXT,
    relation_type TEXT,                -- 'dependency' or 'referencer'
    updated_at TEXT,
    PRIMARY KEY (source_path, target_path, relation_type)
);
CREATE INDEX idx_dep_source ON dependencies(source_path);
CREATE INDEX idx_dep_target ON dependencies(target_path);

-- Full-Text Search Virtual Table (FTS5)
CREATE VIRTUAL TABLE fts_index USING fts5(
    entity_type,                       -- 'asset', 'blueprint', 'actor'
    entity_id,
    name,
    path,
    class_name,
    content,                           -- Aggregated searchable keywords, variables, funcs
    tokenize='porter unicode61'
);
```

---

## 3. Incremental Change Detection & Stale Handling

To ensure index freshness without requiring full roundtrip scans:
1. **Disk Timestamp Matching:**
   When scanning an asset `/Game/Path/To/Asset`:
   - Maps to `Content/Path/To/Asset.uasset` (or `.umap`).
   - Retrieves file modification time `disk_mtime = os.path.getmtime(local_file)`.
   - Compares against cached `mtime` in `assets` table.
   - If `disk_mtime <= cached_mtime`, skips issuing expensive `get_asset_class`, `get_asset_tags`, `get_dependencies`, and `get_referencers` MCP calls.
2. **Stale Asset Flagging:**
   Assets recorded in the database that are not observed during a scan pass are marked with `status = 'stale'`.
3. **Recovery on Corruption / Schema Changes:**
   If the database version changes or a corrupt database is detected, `project_index.py` automatically initializes clean tables and performs an atomic rebuild.

