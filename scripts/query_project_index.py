"""ARC 02 — Search and Context Retrieval Engine

Performs deterministic, token-efficient queries over the persistent SQLite project index,
returning structured, ranked results for AI agents (OpenAI Codex).

Supported Query Modes:
- Exact path lookup
- Asset name (exact & prefix) search
- Asset class/type filtering
- Blueprint variable & function search
- Active level & actor search
- Forward dependencies & reverse referencers
- Multi-tier deterministic search with explicit confidence scoring

Guaranteed read-only: purely reads SQLite database.
"""
import argparse
import json
import sqlite3
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple


class ProjectIndexQuery:
    def __init__(self, db_path: str = 'data/project_index.sqlite'):
        self.db_path = Path(db_path)
        if not self.db_path.exists():
            raise FileNotFoundError(f"Project index database not found at {self.db_path}. Run project_index.py first.")
        self.conn = sqlite3.connect(str(self.db_path))
        self.conn.row_factory = sqlite3.Row

    def close(self):
        if self.conn:
            self.conn.close()

    def get_by_path(self, path: str) -> Optional[Dict[str, Any]]:
        norm_path = path.strip().replace('\\', '/')
        cur = self.conn.execute("SELECT * FROM assets WHERE path = ?;", (norm_path,))
        row = cur.fetchone()
        if not row:
            return None

        result = dict(row)
        result['metadata'] = json.loads(result.pop('metadata_json', '{}'))

        # If it is a blueprint, attach blueprint details
        if result.get('is_blueprint'):
            bp_cur = self.conn.execute("SELECT * FROM blueprints WHERE asset_path = ?;", (norm_path,))
            bp_row = bp_cur.fetchone()
            if bp_row:
                bp_dict = dict(bp_row)
                bp_dict['graphs'] = json.loads(bp_dict.pop('graphs_json', '[]'))
                bp_dict['variables'] = json.loads(bp_dict.pop('variables_json', '[]'))
                bp_dict['functions'] = json.loads(bp_dict.pop('functions_json', '[]'))
                result['blueprint_details'] = bp_dict

        result['relationships'] = self.get_relationships(norm_path)
        return {
            'matched_path': norm_path,
            'asset_type': result.get('class', 'Unknown'),
            'match_reason': 'exact_path',
            'confidence': 1.0,
            'source': 'sqlite_index',
            'freshness': result.get('status', 'active'),
            'record': result,
        }

    def get_relationships(self, path: str) -> Dict[str, List[str]]:
        norm_path = path.strip()
        deps_cur = self.conn.execute(
            "SELECT DISTINCT target_path FROM dependencies WHERE source_path = ? AND relation_type = 'dependency';",
            (norm_path,)
        )
        deps = [r[0] for r in deps_cur.fetchall()]

        refs_cur = self.conn.execute(
            """SELECT DISTINCT source_path FROM dependencies 
               WHERE target_path = ? AND (relation_type = 'referencer' OR relation_type = 'dependency');""",
            (norm_path,)
        )
        refs = [r[0] for r in refs_cur.fetchall()]

        return {
            'dependencies': sorted(deps),
            'referencers': sorted(refs),
        }

    def _enrich_asset_record(self, record: Dict[str, Any]) -> Dict[str, Any]:
        norm_path = record.get('path', '')
        if record.get('is_blueprint'):
            bp_cur = self.conn.execute("SELECT * FROM blueprints WHERE asset_path = ?;", (norm_path,))
            bp_row = bp_cur.fetchone()
            if bp_row:
                bp_dict = dict(bp_row)
                bp_dict['graphs'] = json.loads(bp_dict.pop('graphs_json', '[]'))
                bp_dict['variables'] = json.loads(bp_dict.pop('variables_json', '[]'))
                bp_dict['functions'] = json.loads(bp_dict.pop('functions_json', '[]'))
                record['blueprint_details'] = bp_dict

        record['relationships'] = self.get_relationships(norm_path)
        return record

    def search_by_name(self, name: str, limit: int = 10) -> List[Dict[str, Any]]:
        query_name = name.strip()
        cur = self.conn.execute("""
        SELECT * FROM assets
        WHERE name = ? OR name LIKE ?
        ORDER BY (name = ?) DESC, name ASC
        LIMIT ?;
        """, (query_name, f"%{query_name}%", query_name, limit))

        results = []
        for r in cur.fetchall():
            item = dict(r)
            item['metadata'] = json.loads(item.pop('metadata_json', '{}'))
            item = self._enrich_asset_record(item)
            is_exact = (item['name'].lower() == query_name.lower())
            results.append({
                'matched_path': item['path'],
                'asset_type': item.get('class', 'Unknown'),
                'match_reason': 'exact_name' if is_exact else 'name_substring',
                'confidence': 0.95 if is_exact else 0.80,
                'source': 'sqlite_index',
                'freshness': item.get('status', 'active'),
                'record': item,
            })
        return results

    def search_by_class(self, class_name: str, limit: int = 20) -> List[Dict[str, Any]]:
        query_cls = class_name.strip()
        cur = self.conn.execute("""
        SELECT * FROM assets
        WHERE class = ? OR class LIKE ?
        ORDER BY (class = ?) DESC, name ASC
        LIMIT ?;
        """, (query_cls, f"%{query_cls}%", query_cls, limit))

        results = []
        for r in cur.fetchall():
            item = dict(r)
            item['metadata'] = json.loads(item.pop('metadata_json', '{}'))
            is_exact = (item['class'].lower() == query_cls.lower())
            results.append({
                'matched_path': item['path'],
                'asset_type': item.get('class', 'Unknown'),
                'match_reason': 'exact_class' if is_exact else 'class_substring',
                'confidence': 0.90 if is_exact else 0.75,
                'source': 'sqlite_index',
                'freshness': item.get('status', 'active'),
                'record': item,
            })
        return results

    def search_by_variable(self, var_name: str, limit: int = 10) -> List[Dict[str, Any]]:
        target_var = var_name.strip()
        # Direct query in blueprints table variables_json
        cur = self.conn.execute("""
        SELECT b.*, a.status FROM blueprints b
        JOIN assets a ON a.path = b.asset_path
        WHERE b.variables_json LIKE ?
        LIMIT ?;
        """, (f"%{target_var}%", limit))

        results = []
        for r in cur.fetchall():
            item = dict(r)
            item['variables'] = json.loads(item.pop('variables_json', '[]'))
            item['functions'] = json.loads(item.pop('functions_json', '[]'))
            item['graphs'] = json.loads(item.pop('graphs_json', '[]'))
            results.append({
                'matched_path': item['asset_path'],
                'asset_type': 'Blueprint',
                'match_reason': f"blueprint_variable_match: {target_var}",
                'confidence': 0.90,
                'source': 'sqlite_index',
                'freshness': item.get('status', 'active'),
                'record': item,
            })
        return results

    def search_by_function(self, func_name: str, limit: int = 10) -> List[Dict[str, Any]]:
        target_fn = func_name.strip()
        cur = self.conn.execute("""
        SELECT b.*, a.status FROM blueprints b
        JOIN assets a ON a.path = b.asset_path
        WHERE b.functions_json LIKE ?
        LIMIT ?;
        """, (f"%{target_fn}%", limit))

        results = []
        for r in cur.fetchall():
            item = dict(r)
            item['variables'] = json.loads(item.pop('variables_json', '[]'))
            item['functions'] = json.loads(item.pop('functions_json', '[]'))
            item['graphs'] = json.loads(item.pop('graphs_json', '[]'))
            results.append({
                'matched_path': item['asset_path'],
                'asset_type': 'Blueprint',
                'match_reason': f"blueprint_function_match: {target_fn}",
                'confidence': 0.90,
                'source': 'sqlite_index',
                'freshness': item.get('status', 'active'),
                'record': item,
            })
        return results

    def search_actors(self, level_path: Optional[str] = None, label: Optional[str] = None,
                      class_name: Optional[str] = None, limit: int = 25) -> List[Dict[str, Any]]:
        conditions = []
        params = []
        if level_path:
            conditions.append("level_path = ?")
            params.append(level_path.strip())
        if label:
            conditions.append("(label = ? OR label LIKE ?)")
            params.extend([label.strip(), f"%{label.strip()}%"])
        if class_name:
            conditions.append("(class = ? OR class LIKE ?)")
            params.extend([class_name.strip(), f"%{class_name.strip()}%"])

        where_clause = f"WHERE {' AND '.join(conditions)}" if conditions else ""
        query = f"SELECT * FROM actors {where_clause} ORDER BY label ASC LIMIT ?;"
        params.append(limit)

        cur = self.conn.execute(query, params)
        results = []
        for r in cur.fetchall():
            item = dict(r)
            item['components'] = json.loads(item.pop('components_json', '[]'))
            item['tags'] = json.loads(item.pop('tags_json', '[]'))
            results.append({
                'matched_path': item['ref_path'],
                'asset_type': item.get('class', 'Actor'),
                'match_reason': 'actor_search',
                'confidence': 0.85,
                'source': 'sqlite_index',
                'freshness': 'active',
                'record': item,
            })
        return results

    def general_search(self, query: str, limit: int = 10) -> List[Dict[str, Any]]:
        """Multi-stage deterministic search (Exact Path -> Exact Name -> Variable/Function -> FTS5)."""
        q = query.strip()
        seen_paths = set()
        ranked_results: List[Dict[str, Any]] = []

        # Stage 1: Exact Path
        if '/' in q:
            exact = self.get_by_path(q)
            if exact:
                seen_paths.add(exact['matched_path'])
                ranked_results.append(exact)

        # Stage 2: Exact Name
        for item in self.search_by_name(q, limit=limit):
            if item['matched_path'] not in seen_paths and item['confidence'] >= 0.9:
                seen_paths.add(item['matched_path'])
                ranked_results.append(item)

        # Stage 3: Variable & Function Matches
        for item in self.search_by_variable(q, limit=limit):
            if item['matched_path'] not in seen_paths:
                seen_paths.add(item['matched_path'])
                ranked_results.append(item)

        for item in self.search_by_function(q, limit=limit):
            if item['matched_path'] not in seen_paths:
                seen_paths.add(item['matched_path'])
                ranked_results.append(item)

        # Stage 4: FTS5 Full-Text Search
        if len(ranked_results) < limit:
            clean_q = ''.join(c for c in q if c.isalnum() or c.isspace()).strip()
            if clean_q:
                try:
                    fts_cur = self.conn.execute("""
                    SELECT entity_type, entity_id, name, path, class_name
                    FROM fts_index
                    WHERE fts_index MATCH ?
                    LIMIT ?;
                    """, (f"{clean_q}*", limit - len(ranked_results)))
                    for row in fts_cur.fetchall():
                        p = row['path']
                        if p not in seen_paths:
                            seen_paths.add(p)
                            ranked_results.append({
                                'matched_path': p,
                                'asset_type': row['class_name'],
                                'match_reason': f"fts_match ({row['entity_type']})",
                                'confidence': 0.70,
                                'source': 'sqlite_index',
                                'freshness': 'active',
                                'record': {'name': row['name'], 'path': p, 'class': row['class_name']},
                            })
                except Exception:
                    pass

        return ranked_results[:limit]


def format_search_markdown(results: List[Dict[str, Any]], query_label: str = '') -> str:
    if not results:
        return f"No results found for query: `{query_label}`"

    lines = [f"### Project Index Search Results: `{query_label}` ({len(results)} matches)"]
    for i, r in enumerate(results, 1):
        rec = r.get('record', {})
        path = r.get('matched_path', '')
        cls = r.get('asset_type', '')
        reason = r.get('match_reason', '')
        conf = r.get('confidence', 0.0)

        lines.append(f"**{i}. {rec.get('name', path.split('/')[-1])}** (`{cls}`) — Confidence: {conf * 100:.0f}%")
        lines.append(f"   - **Path:** `{path}`")
        lines.append(f"   - **Match Reason:** {reason}")

        if 'blueprint_details' in rec:
            bp = rec['blueprint_details']
            lines.append(f"   - **Parent Class:** `{bp.get('parent_class') or bp.get('native_parent', 'N/A')}`")
            lines.append(f"   - **Graphs:** {', '.join(bp.get('graphs', [])[:4])}")
            lines.append(f"   - **Variables:** {', '.join([str(v) for v in bp.get('variables', [])[:6]])}")

        if 'relationships' in r.get('record', {}):
            rel = r['record']['relationships']
            if rel.get('dependencies'):
                lines.append(f"   - **Direct Dependencies ({len(rel['dependencies'])}):** {', '.join(rel['dependencies'][:3])}")
            if rel.get('referencers'):
                lines.append(f"   - **Direct Referencers ({len(rel['referencers'])}):** {', '.join(rel['referencers'][:3])}")

    return '\n'.join(lines)


def main():
    parser = argparse.ArgumentParser(description='ARC 02 Search and Context Retrieval Engine')
    parser.add_argument('--db', default='data/project_index.sqlite', help='SQLite database path')
    parser.add_argument('-q', '--query', help='General multi-tier search query')
    parser.add_argument('--path', help='Exact package path lookup')
    parser.add_argument('--name', help='Search by asset name')
    parser.add_argument('--type', help='Search by asset class/type')
    parser.add_argument('--variable', help='Search Blueprints by variable name')
    parser.add_argument('--function', help='Search Blueprints by function name')
    parser.add_argument('--actor', help='Search scene actors by label or class')
    parser.add_argument('--limit', type=int, default=10, help='Max results to return')
    parser.add_argument('--json', action='store_true', help='Output raw JSON instead of markdown')
    args = parser.parse_args()

    engine = ProjectIndexQuery(args.db)
    results = []
    label = ''

    if args.path:
        exact = engine.get_by_path(args.path)
        results = [exact] if exact else []
        label = f"path:{args.path}"
    elif args.name:
        results = engine.search_by_name(args.name, limit=args.limit)
        label = f"name:{args.name}"
    elif args.type:
        results = engine.search_by_class(args.type, limit=args.limit)
        label = f"type:{args.type}"
    elif args.variable:
        results = engine.search_by_variable(args.variable, limit=args.limit)
        label = f"variable:{args.variable}"
    elif args.function:
        results = engine.search_by_function(args.function, limit=args.limit)
        label = f"function:{args.function}"
    elif args.actor:
        results = engine.search_actors(label=args.actor, limit=args.limit)
        label = f"actor:{args.actor}"
    elif args.query:
        results = engine.general_search(args.query, limit=args.limit)
        label = args.query
    else:
        print("Please specify a search parameter (e.g. -q, --name, --type, --variable, --function, --actor).")
        return 1

    if args.json:
        print(json.dumps(results, indent=2))
    else:
        print(format_search_markdown(results, label))

    engine.close()
    return 0


if __name__ == '__main__':
    main()
