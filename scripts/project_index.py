"""ARC 02 — Persistent Project Indexing Engine (SQLite + FTS5)

Maintains an indexed, queryable SQLite cache of:
- Project identity and metadata
- Asset inventory (/Game assets, classes, package hierarchy)
- Actor and scene hierarchy
- Blueprint structures (graphs, variables, functions, AST summaries)
- Forward and reverse asset dependencies
- Full-Text Search (FTS5) index for token-efficient retrieval

Enforces strict read-only execution: zero project mutations.
"""
import argparse
import datetime
import hashlib
import json
import logging
import os
import sqlite3
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple

logger = logging.getLogger("project_index")

CURRENT_SCHEMA_VERSION = 1


def hash_id(identifier: str) -> str:
    return hashlib.sha256(identifier.strip().encode('utf-8')).hexdigest()[:16]


def normalize_package_path(path: str) -> str:
    p = path.strip().replace('\\', '/')
    if p.endswith('.uasset') or p.endswith('.umap'):
        p = p.rsplit('.', 1)[0]
    return p


class ProjectIndexDB:
    def __init__(self, db_path: str = 'data/project_index.sqlite'):
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self.conn = sqlite3.connect(str(self.db_path))
        self.conn.row_factory = sqlite3.Row
        self._init_schema()

    def _init_schema(self):
        with self.conn:
            # Metadata table
            self.conn.execute("""
            CREATE TABLE IF NOT EXISTS meta (
                key TEXT PRIMARY KEY,
                value TEXT,
                updated_at TEXT
            );
            """)

            # Assets table
            self.conn.execute("""
            CREATE TABLE IF NOT EXISTS assets (
                id TEXT PRIMARY KEY,
                path TEXT UNIQUE,
                name TEXT,
                class TEXT,
                package_folder TEXT,
                is_blueprint INTEGER DEFAULT 0,
                parent_class TEXT,
                native_parent TEXT,
                item_type TEXT,
                metadata_json TEXT,
                mtime REAL DEFAULT 0,
                status TEXT DEFAULT 'active',
                updated_at TEXT
            );
            """)
            self.conn.execute("CREATE INDEX IF NOT EXISTS idx_assets_name ON assets(name);")
            self.conn.execute("CREATE INDEX IF NOT EXISTS idx_assets_class ON assets(class);")
            self.conn.execute("CREATE INDEX IF NOT EXISTS idx_assets_folder ON assets(package_folder);")

            # Blueprints table
            self.conn.execute("""
            CREATE TABLE IF NOT EXISTS blueprints (
                asset_path TEXT PRIMARY KEY,
                name TEXT,
                parent_class TEXT,
                native_parent TEXT,
                item_type TEXT,
                graph_count INTEGER DEFAULT 0,
                variable_count INTEGER DEFAULT 0,
                function_count INTEGER DEFAULT 0,
                graphs_json TEXT,
                variables_json TEXT,
                functions_json TEXT,
                dsl_summary TEXT,
                updated_at TEXT,
                FOREIGN KEY (asset_path) REFERENCES assets(path) ON DELETE CASCADE
            );
            """)

            # Scene Actors table
            self.conn.execute("""
            CREATE TABLE IF NOT EXISTS actors (
                id TEXT PRIMARY KEY,
                level_path TEXT,
                ref_path TEXT UNIQUE,
                label TEXT,
                class TEXT,
                location_x REAL,
                location_y REAL,
                location_z REAL,
                rotation_p REAL,
                rotation_y REAL,
                rotation_r REAL,
                scale_x REAL,
                scale_y REAL,
                scale_z REAL,
                component_count INTEGER DEFAULT 0,
                components_json TEXT,
                tags_json TEXT,
                updated_at TEXT
            );
            """)
            self.conn.execute("CREATE INDEX IF NOT EXISTS idx_actors_level ON actors(level_path);")
            self.conn.execute("CREATE INDEX IF NOT EXISTS idx_actors_label ON actors(label);")
            self.conn.execute("CREATE INDEX IF NOT EXISTS idx_actors_class ON actors(class);")

            # Dependencies table
            self.conn.execute("""
            CREATE TABLE IF NOT EXISTS dependencies (
                source_path TEXT,
                target_path TEXT,
                relation_type TEXT,
                updated_at TEXT,
                PRIMARY KEY (source_path, target_path, relation_type)
            );
            """)
            self.conn.execute("CREATE INDEX IF NOT EXISTS idx_dep_source ON dependencies(source_path);")
            self.conn.execute("CREATE INDEX IF NOT EXISTS idx_dep_target ON dependencies(target_path);")

            # Full-Text Search (FTS5)
            self.conn.execute("""
            CREATE VIRTUAL TABLE IF NOT EXISTS fts_index USING fts5(
                entity_type,
                entity_id,
                name,
                path,
                class_name,
                content,
                tokenize='porter unicode61'
            );
            """)

            # Store schema version
            now = datetime.datetime.now(datetime.timezone.utc).isoformat()
            self.conn.execute("""
            INSERT OR REPLACE INTO meta (key, value, updated_at)
            VALUES ('schema_version', ?, ?);
            """, (str(CURRENT_SCHEMA_VERSION), now))

    def close(self):
        if self.conn:
            self.conn.close()

    def set_meta(self, key: str, value: Any):
        now = datetime.datetime.now(datetime.timezone.utc).isoformat()
        val_str = json.dumps(value) if not isinstance(value, str) else value
        with self.conn:
            self.conn.execute("INSERT OR REPLACE INTO meta (key, value, updated_at) VALUES (?, ?, ?);",
                              (key, val_str, now))

    def get_meta(self, key: str) -> Optional[str]:
        cur = self.conn.execute("SELECT value FROM meta WHERE key = ?;", (key,))
        row = cur.fetchone()
        return row[0] if row else None

    def upsert_asset(self, path: str, name: str, class_name: str,
                     package_folder: str, is_blueprint: bool = False,
                     parent_class: str = '', native_parent: str = '',
                     item_type: str = '', metadata: Optional[Dict] = None,
                     mtime: float = 0.0, status: str = 'active') -> str:
        aid = hash_id(path)
        now = datetime.datetime.now(datetime.timezone.utc).isoformat()
        meta_json = json.dumps(metadata or {})
        with self.conn:
            self.conn.execute("""
            INSERT OR REPLACE INTO assets (
                id, path, name, class, package_folder, is_blueprint,
                parent_class, native_parent, item_type, metadata_json,
                mtime, status, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?);
            """, (aid, path, name, class_name, package_folder, 1 if is_blueprint else 0,
                  parent_class, native_parent, item_type, meta_json, mtime, status, now))

            # Update FTS5
            content_pieces = [name, path, class_name, parent_class, native_parent, item_type, meta_json]
            content_str = ' '.join(p for p in content_pieces if p)
            self.conn.execute("DELETE FROM fts_index WHERE entity_id = ?;", (aid,))
            self.conn.execute("""
            INSERT INTO fts_index (entity_type, entity_id, name, path, class_name, content)
            VALUES ('asset', ?, ?, ?, ?, ?);
            """, (aid, name, path, class_name, content_str))

        return aid

    def upsert_blueprint(self, asset_path: str, name: str,
                         parent_class: str = '', native_parent: str = '',
                         item_type: str = '', graphs: Optional[List] = None,
                         variables: Optional[List] = None, functions: Optional[List] = None,
                         dsl_summary: str = ''):
        now = datetime.datetime.now(datetime.timezone.utc).isoformat()
        graphs = graphs or []
        variables = variables or []
        functions = functions or []
        graphs_json = json.dumps(graphs)
        vars_json = json.dumps(variables)
        funcs_json = json.dumps(functions)
        bid = f"bp:{hash_id(asset_path)}"

        with self.conn:
            self.conn.execute("""
            INSERT OR REPLACE INTO blueprints (
                asset_path, name, parent_class, native_parent, item_type,
                graph_count, variable_count, function_count,
                graphs_json, variables_json, functions_json, dsl_summary, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?);
            """, (asset_path, name, parent_class, native_parent, item_type,
                  len(graphs), len(variables), len(functions),
                  graphs_json, vars_json, funcs_json, dsl_summary, now))

            # Index Blueprint elements in FTS
            content_tokens = [name, asset_path, parent_class, native_parent, item_type, dsl_summary]
            for g in graphs:
                content_tokens.append(str(g))
            for v in variables:
                content_tokens.append(str(v))
            for f in functions:
                content_tokens.append(f.get('name', '') if isinstance(f, dict) else str(f))

            content_str = ' '.join(content_tokens)
            self.conn.execute("DELETE FROM fts_index WHERE entity_id = ?;", (bid,))
            self.conn.execute("""
            INSERT INTO fts_index (entity_type, entity_id, name, path, class_name, content)
            VALUES ('blueprint', ?, ?, ?, 'Blueprint', ?);
            """, (bid, name, asset_path, content_str))

    def upsert_actor(self, level_path: str, ref_path: str, label: str,
                     class_name: str, transform: Optional[Dict] = None,
                     components: Optional[List] = None, tags: Optional[List] = None) -> str:
        aid = hash_id(ref_path)
        now = datetime.datetime.now(datetime.timezone.utc).isoformat()
        loc = (transform or {}).get('location', {})
        rot = (transform or {}).get('rotation', {})
        scl = (transform or {}).get('scale', {})
        comps = components or []
        tags = tags or []
        comps_json = json.dumps(comps)
        tags_json = json.dumps(tags)

        with self.conn:
            self.conn.execute("""
            INSERT OR REPLACE INTO actors (
                id, level_path, ref_path, label, class,
                location_x, location_y, location_z,
                rotation_p, rotation_y, rotation_r,
                scale_x, scale_y, scale_z,
                component_count, components_json, tags_json, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?);
            """, (aid, level_path, ref_path, label, class_name,
                  loc.get('x', 0.0), loc.get('y', 0.0), loc.get('z', 0.0),
                  rot.get('pitch', 0.0), rot.get('yaw', 0.0), rot.get('roll', 0.0),
                  scl.get('x', 1.0), scl.get('y', 1.0), scl.get('z', 1.0),
                  len(comps), comps_json, tags_json, now))

            content_str = f"{label} {class_name} {ref_path} {' '.join(tags)}"
            self.conn.execute("DELETE FROM fts_index WHERE entity_id = ?;", (aid,))
            self.conn.execute("""
            INSERT INTO fts_index (entity_type, entity_id, name, path, class_name, content)
            VALUES ('actor', ?, ?, ?, ?, ?);
            """, (aid, label, ref_path, class_name, content_str))

        return aid

    def upsert_dependency(self, source_path: str, target_path: str, relation_type: str = 'dependency'):
        now = datetime.datetime.now(datetime.timezone.utc).isoformat()
        with self.conn:
            self.conn.execute("""
            INSERT OR REPLACE INTO dependencies (source_path, target_path, relation_type, updated_at)
            VALUES (?, ?, ?, ?);
            """, (source_path, target_path, relation_type, now))

    def mark_stale_unseen(self, seen_asset_paths: Set[str]):
        """Marks assets not seen in the current indexing pass as stale."""
        now = datetime.datetime.now(datetime.timezone.utc).isoformat()
        with self.conn:
            cur = self.conn.execute("SELECT path FROM assets WHERE status = 'active';")
            all_active = [r[0] for r in cur.fetchall()]
            for p in all_active:
                if p not in seen_asset_paths:
                    self.conn.execute("UPDATE assets SET status = 'stale', updated_at = ? WHERE path = ?;", (now, p))

    def get_stats(self) -> Dict[str, Any]:
        with self.conn:
            asset_count = self.conn.execute("SELECT count(*) FROM assets;").fetchone()[0]
            active_assets = self.conn.execute("SELECT count(*) FROM assets WHERE status = 'active';").fetchone()[0]
            stale_assets = self.conn.execute("SELECT count(*) FROM assets WHERE status = 'stale';").fetchone()[0]
            bp_count = self.conn.execute("SELECT count(*) FROM blueprints;").fetchone()[0]
            actor_count = self.conn.execute("SELECT count(*) FROM actors;").fetchone()[0]
            dep_count = self.conn.execute("SELECT count(*) FROM dependencies;").fetchone()[0]
            fts_count = self.conn.execute("SELECT count(*) FROM fts_index;").fetchone()[0]

            classes_cur = self.conn.execute("SELECT class, count(*) as c FROM assets GROUP BY class ORDER BY c DESC LIMIT 5;")
            top_classes = {r[0]: r[1] for r in classes_cur.fetchall()}

        return {
            'database_path': str(self.db_path),
            'database_size_bytes': self.db_path.stat().st_size if self.db_path.exists() else 0,
            'total_assets': asset_count,
            'active_assets': active_assets,
            'stale_assets': stale_assets,
            'blueprints_indexed': bp_count,
            'actors_indexed': actor_count,
            'dependencies_indexed': dep_count,
            'fts_records': fts_count,
            'top_classes': top_classes,
        }


def resolve_local_asset_mtime(project_dir: Path, package_path: str) -> float:
    """Finds matching .uasset or .umap in Content/ to retrieve disk mtime for incremental change detection."""
    if not package_path.startswith('/Game/'):
        return 0.0
    rel_part = package_path[len('/Game/'):]
    content_dir = project_dir / 'Content'
    candidate_uasset = content_dir / f"{rel_part}.uasset"
    candidate_umap = content_dir / f"{rel_part}.umap"
    if candidate_uasset.is_file():
        return candidate_uasset.stat().st_mtime
    if candidate_umap.is_file():
        return candidate_umap.stat().st_mtime
    return 0.0


def build_project_index(session, project_path: Path, engine_path: Path,
                        db_path: str = 'data/project_index.sqlite',
                        asset_limit: int = 150, actor_limit: int = 100,
                        blueprint_limit: int = 30, incremental: bool = True) -> Dict[str, Any]:
    db = ProjectIndexDB(db_path=db_path)
    identity = session.verify_identity(project_path, engine_path)
    current_level = session.invoke('SceneTools', 'get_current_level')

    db.set_meta('project_name', project_path.stem)
    db.set_meta('project_file', str(project_path))
    db.set_meta('engine_path', str(engine_path))
    db.set_meta('active_level', current_level)
    db.set_meta('last_scan_utc', datetime.datetime.now(datetime.timezone.utc).isoformat())

    project_dir = project_path.parent
    seen_paths: Set[str] = set()
    new_or_updated = 0
    skipped_unchanged = 0

    # 1. Index Assets in /Game
    raw_assets = session.invoke('AssetTools', 'find_assets', folder_path='/Game', name='', recursive=True)
    if isinstance(raw_assets, list):
        for path in raw_assets[:asset_limit]:
            norm_path = normalize_package_path(path)
            seen_paths.add(norm_path)
            name = norm_path.split('/')[-1]
            folder = '/'.join(norm_path.split('/')[:-1])

            disk_mtime = resolve_local_asset_mtime(project_dir, norm_path)

            # Check if incremental refresh can skip querying MCP
            if incremental and disk_mtime > 0:
                cur = db.conn.execute("SELECT mtime, class FROM assets WHERE path = ?;", (norm_path,))
                row = cur.fetchone()
                if row and row['mtime'] >= disk_mtime:
                    skipped_unchanged += 1
                    continue

            # Query class and metadata
            cls_name = 'Unknown'
            try:
                c = session.invoke('AssetTools', 'get_asset_class', asset_path=path)
                cls_name = str(c)
            except Exception:
                pass

            tags = {}
            try:
                t = session.invoke('AssetTools', 'get_asset_tags', asset_path=path)
                if isinstance(t, dict):
                    tags = t
            except Exception:
                pass

            parent_cls = tags.get('ParentClass', '')
            native_parent = tags.get('NativeParentClass', '')
            item_type = tags.get('ItemTypeDisplayName', tags.get('ItemType', ''))
            is_bp = cls_name.endswith('_C') or 'Blueprint' in cls_name or bool(parent_cls)

            db.upsert_asset(
                path=norm_path,
                name=name,
                class_name=cls_name,
                package_folder=folder,
                is_blueprint=is_bp,
                parent_class=parent_cls,
                native_parent=native_parent,
                item_type=item_type,
                metadata=tags,
                mtime=disk_mtime,
                status='active',
            )
            new_or_updated += 1

            # Dependencies
            try:
                deps = session.invoke('AssetTools', 'get_dependencies', asset_path=path)
                if isinstance(deps, list):
                    for d in deps:
                        db.upsert_dependency(norm_path, normalize_package_path(d), 'dependency')
            except Exception:
                pass

            # Referencers
            try:
                refs = session.invoke('AssetTools', 'get_referencers', asset_path=path)
                if isinstance(refs, list):
                    for r in refs:
                        db.upsert_dependency(normalize_package_path(r), norm_path, 'referencer')
            except Exception:
                pass

    db.mark_stale_unseen(seen_paths)

    # 2. Index Blueprints in detail
    session.load_toolset('BlueprintTools')
    cur = db.conn.execute("SELECT path, name, parent_class, native_parent, item_type FROM assets WHERE is_blueprint = 1 LIMIT ?;", (blueprint_limit,))
    bps_to_inspect = cur.fetchall()

    for bp in bps_to_inspect:
        bp_path = bp['path']
        bp_name = bp['name']
        ref = {'refPath': f"{bp_path}.{bp_name}"}

        graphs = []
        try:
            g_list = session.invoke('BlueprintTools', 'list_graphs', blueprint=ref)
            if isinstance(g_list, list):
                graphs = [g.get('refPath', '').split('.')[-1] if isinstance(g, dict) else str(g) for g in g_list]
        except Exception:
            pass

        variables = []
        try:
            v_list = session.invoke('BlueprintTools', 'list_variables', blueprint=ref)
            if isinstance(v_list, list):
                variables = v_list
        except Exception:
            pass

        functions = []
        try:
            f_list = session.invoke('BlueprintTools', 'list_functions', blueprint=ref)
            if isinstance(f_list, list):
                functions = f_list
        except Exception:
            pass

        # Parse EventGraph DSL if available
        dsl_summary = ''
        event_graph_ref = f"{bp_path}.{bp_name}:EventGraph"
        try:
            dsl = session.invoke('BlueprintTools', 'read_graph_dsl', graph={'refPath': event_graph_ref})
            if dsl and isinstance(dsl, str) and dsl.strip():
                from blueprint_parser import summarize_dsl
                s = summarize_dsl(dsl)
                dsl_summary = s.get('summary', '')
        except Exception:
            pass

        db.upsert_blueprint(
            asset_path=bp_path,
            name=bp_name,
            parent_class=bp['parent_class'],
            native_parent=bp['native_parent'],
            item_type=bp['item_type'],
            graphs=graphs,
            variables=variables,
            functions=functions,
            dsl_summary=dsl_summary,
        )

    # 3. Index Scene Actors in Active Level
    actor_refs = session.invoke('SceneTools', 'find_actors', name='', tag='', collision_channels=[])
    if isinstance(actor_refs, list):
        for ref in actor_refs[:actor_limit]:
            ref_path = ref.get('refPath', '')
            label = ''
            try:
                label = session.invoke('ActorTools', 'get_label', actor=ref)
            except Exception:
                pass

            cls_name = 'Actor'
            try:
                c = session.invoke('ObjectTools', 'get_class', instance=ref)
                cls_name = c.get('refPath', '').split('.')[-1] if isinstance(c, dict) else str(c)
            except Exception:
                pass

            transform = {}
            try:
                transform = session.invoke('ActorTools', 'get_actor_transform', actor=ref)
            except Exception:
                pass

            components = []
            try:
                comps = session.invoke('ActorTools', 'get_components', actor=ref)
                if isinstance(comps, list):
                    for c_ref in comps:
                        c_cls = 'Component'
                        try:
                            c_info = session.invoke('ObjectTools', 'get_class', instance=c_ref)
                            c_cls = c_info.get('refPath', '').split('.')[-1] if isinstance(c_info, dict) else str(c_info)
                        except Exception:
                            pass
                        components.append({'refPath': c_ref.get('refPath', ''), 'class': c_cls})
            except Exception:
                pass

            tags = []
            try:
                tags = session.invoke('ActorTools', 'get_tags', actor=ref)
            except Exception:
                pass

            db.upsert_actor(
                level_path=current_level,
                ref_path=ref_path,
                label=label,
                class_name=cls_name,
                transform=transform,
                components=components,
                tags=tags,
            )

    stats = db.get_stats()
    stats['new_or_updated'] = new_or_updated
    stats['skipped_unchanged'] = skipped_unchanged
    db.close()
    return stats


def main():
    parser = argparse.ArgumentParser(description='ARC 02 Persistent Project Index Engine (SQLite + FTS5)')
    parser.add_argument('--project', required=True, type=Path, help='Path to .uproject file')
    parser.add_argument('--engine', required=True, type=Path, help='Path to Unreal Engine directory')
    parser.add_argument('--endpoint', default='http://127.0.0.1:8000/mcp')
    parser.add_argument('--db', default='data/project_index.sqlite', help='SQLite database path')
    parser.add_argument('--asset-limit', type=int, default=150, help='Max assets to index')
    parser.add_argument('--actor-limit', type=int, default=100, help='Max actors to index')
    parser.add_argument('--blueprint-limit', type=int, default=30, help='Max blueprints to index')
    parser.add_argument('--no-incremental', action='store_true', help='Force full re-index without skipping unchanged mtimes')
    parser.add_argument('--stats', action='store_true', help='Print database statistics and exit')
    args = parser.parse_args()

    db_path = Path(args.db)

    if args.stats:
        if not db_path.exists():
            print(f"Error: Database file does not exist at {db_path}")
            return 1
        db = ProjectIndexDB(str(db_path))
        print(json.dumps(db.get_stats(), indent=2))
        db.close()
        return 0

    from unreal_session import UnrealSession

    session = UnrealSession(endpoint=args.endpoint)
    session.connect(full=False)

    print(f"Building project index into {db_path}...")
    stats = build_project_index(
        session=session,
        project_path=args.project.resolve(),
        engine_path=args.engine.resolve(),
        db_path=str(db_path),
        asset_limit=args.asset_limit,
        actor_limit=args.actor_limit,
        blueprint_limit=args.blueprint_limit,
        incremental=not args.no_incremental,
    )

    print("Index build complete!")
    print(json.dumps(stats, indent=2))
    return 0


if __name__ == '__main__':
    main()

