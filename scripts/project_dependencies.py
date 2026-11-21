"""ARC 02 — Asset Dependency Graph & Impact Analysis Engine

Constructs, queries, and analyzes forward and reverse asset dependency graphs
for Unreal Engine projects using native AssetTools.

Capabilities:
- Forward dependencies (what does asset X require?)
- Reverse referencers (what requires asset X?)
- Transitive dependencies and impact blast-radius analysis (with depth bounding)
- Cycle detection & Tarjan's Strongly Connected Components (SCC)
- Unresolved / missing reference detection
- Read-only execution with zero project mutations
"""
import argparse
import json
import logging
from collections import defaultdict, deque
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple

logger = logging.getLogger("project_dependencies")


class AssetDependencyGraph:
    def __init__(self):
        # path -> metadata dict
        self.nodes: Dict[str, Dict[str, Any]] = {}
        # source -> set of targets (source depends on target)
        self.forward_adj: Dict[str, Set[str]] = defaultdict(set)
        # target -> set of sources (source references target)
        self.reverse_adj: Dict[str, Set[str]] = defaultdict(set)
        # (source, target) -> edge type ('hard_reference', 'soft_reference', 'script_module', etc.)
        self.edge_types: Dict[Tuple[str, str], str] = {}

    def add_node(self, path: str, asset_type: Optional[str] = None, exists: bool = True, metadata: Optional[Dict] = None):
        norm_path = path.strip()
        if norm_path not in self.nodes:
            short_name = norm_path.split('/')[-1].split(':')[-1]
            category = 'project'
            if norm_path.startswith('/Script/'):
                category = 'native_script'
                if not asset_type:
                    asset_type = 'NativePackage'
            elif norm_path.startswith('/Engine/'):
                category = 'engine_asset'
            elif norm_path.startswith('/Game/'):
                category = 'game_asset'

            self.nodes[norm_path] = {
                'path': norm_path,
                'name': short_name,
                'class': asset_type or 'Unknown',
                'category': category,
                'exists': exists,
                'metadata': metadata or {},
            }
        else:
            if asset_type and self.nodes[norm_path]['class'] in ('Unknown', None):
                self.nodes[norm_path]['class'] = asset_type
            if metadata:
                self.nodes[norm_path]['metadata'].update(metadata)

    def add_edge(self, source: str, target: str, edge_type: str = 'reference'):
        src = source.strip()
        tgt = target.strip()
        if not src or not tgt or src == tgt:
            return
        if src not in self.nodes:
            self.add_node(src)
        if tgt not in self.nodes:
            self.add_node(tgt)

        self.forward_adj[src].add(tgt)
        self.reverse_adj[tgt].add(src)
        self.edge_types[(src, tgt)] = edge_type

    def get_direct_dependencies(self, path: str) -> List[str]:
        return sorted(list(self.forward_adj.get(path.strip(), set())))

    def get_direct_referencers(self, path: str) -> List[str]:
        return sorted(list(self.reverse_adj.get(path.strip(), set())))

    def get_transitive_dependencies(self, path: str, max_depth: int = 5) -> Dict[str, Any]:
        start = path.strip()
        visited: Dict[str, int] = {}
        queue: deque = deque([(start, 0)])

        while queue:
            curr, depth = queue.popleft()
            if curr in visited and visited[curr] <= depth:
                continue
            visited[curr] = depth
            if depth < max_depth:
                for neighbor in sorted(self.forward_adj.get(curr, set())):
                    if neighbor not in visited or visited[neighbor] > depth + 1:
                        queue.append((neighbor, depth + 1))

        # Exclude starting node from returned dependency set
        visited.pop(start, None)
        return {
            'root': start,
            'max_depth_applied': max_depth,
            'total_dependencies': len(visited),
            'dependencies_by_depth': {
                d: [k for k, v in visited.items() if v == d]
                for d in range(1, max_depth + 1) if any(v == d for v in visited.values())
            },
            'all_dependencies': sorted(list(visited.keys())),
        }

    def get_affected_assets(self, path: str, max_depth: int = 5) -> Dict[str, Any]:
        """Calculates blast radius when modifying an asset by traversing reverse referencers."""
        start = path.strip()
        visited: Dict[str, int] = {}
        queue: deque = deque([(start, 0)])

        while queue:
            curr, depth = queue.popleft()
            if curr in visited and visited[curr] <= depth:
                continue
            visited[curr] = depth
            if depth < max_depth:
                for parent in sorted(self.reverse_adj.get(curr, set())):
                    if parent not in visited or visited[parent] > depth + 1:
                        queue.append((parent, depth + 1))

        visited.pop(start, None)
        immediate = [k for k, v in visited.items() if v == 1]
        transitive = [k for k, v in visited.items() if v > 1]

        return {
            'target_asset': start,
            'max_depth_applied': max_depth,
            'total_potentially_affected': len(visited),
            'immediate_referencers': immediate,
            'transitive_referencers': transitive,
            'impact_by_depth': {
                d: [k for k, v in visited.items() if v == d]
                for d in range(1, max_depth + 1) if any(v == d for v in visited.values())
            },
            'potential_risk_level': 'HIGH' if len(visited) > 10 else ('MEDIUM' if len(visited) > 3 else ('LOW' if visited else 'NONE')),
            'assessment_note': 'Lists assets with potential compilation or runtime dependencies. Verification required before deletion or signature change.'
        }

    def find_cycles(self) -> List[List[str]]:
        """Finds directed cycles in the dependency graph using DFS."""
        visited: Set[str] = set()
        stack: List[str] = []
        in_stack: Set[str] = set()
        cycles: List[List[str]] = []
        seen_cycles: Set[str] = set()

        def dfs(node: str):
            visited.add(node)
            stack.append(node)
            in_stack.add(node)

            for neighbor in self.forward_adj.get(node, set()):
                if neighbor not in visited:
                    dfs(neighbor)
                elif neighbor in in_stack:
                    idx = stack.index(neighbor)
                    cycle = stack[idx:] + [neighbor]
                    cycle_key = '->'.join(sorted(cycle))
                    if cycle_key not in seen_cycles:
                        seen_cycles.add(cycle_key)
                        cycles.append(cycle)

            stack.pop()
            in_stack.remove(node)

        for n in sorted(list(self.nodes.keys())):
            if n not in visited:
                dfs(n)

        return cycles

    def find_strongly_connected_components(self) -> List[List[str]]:
        """Tarjan's algorithm for finding SCCs with more than 1 node (circular dependency clusters)."""
        idx = 0
        indices: Dict[str, int] = {}
        lowlinks: Dict[str, int] = {}
        on_stack: Set[str] = set()
        stack: List[str] = []
        sccs: List[List[str]] = []

        def strongconnect(v: str):
            nonlocal idx
            indices[v] = idx
            lowlinks[v] = idx
            idx += 1
            stack.append(v)
            on_stack.add(v)

            for w in self.forward_adj.get(v, set()):
                if w not in indices:
                    strongconnect(w)
                    lowlinks[v] = min(lowlinks[v], lowlinks[w])
                elif w in on_stack:
                    lowlinks[v] = min(lowlinks[v], indices[w])

            if lowlinks[v] == indices[v]:
                scc = []
                while True:
                    w = stack.pop()
                    on_stack.remove(w)
                    scc.append(w)
                    if w == v:
                        break
                if len(scc) > 1:
                    sccs.append(sorted(scc))

        for node in sorted(list(self.nodes.keys())):
            if node not in indices:
                strongconnect(node)

        return sccs

    def find_unresolved_references(self) -> List[Dict[str, Any]]:
        """Identifies references pointing to nodes marked as missing or nonexistent."""
        unresolved = []
        for src, targets in self.forward_adj.items():
            for tgt in targets:
                node = self.nodes.get(tgt)
                if not node or not node.get('exists', True):
                    unresolved.append({
                        'referencer': src,
                        'missing_target': tgt,
                        'edge_type': self.edge_types.get((src, tgt), 'reference')
                    })
        return unresolved

    def summarize_asset(self, path: str, max_depth: int = 2) -> Dict[str, Any]:
        """Compact summary of an asset's position in the dependency graph."""
        norm_path = path.strip()
        node = self.nodes.get(norm_path, {'path': norm_path, 'name': norm_path.split('/')[-1], 'class': 'Unknown'})
        deps = self.get_transitive_dependencies(norm_path, max_depth=max_depth)
        affected = self.get_affected_assets(norm_path, max_depth=max_depth)

        return {
            'asset': node,
            'direct_dependency_count': len(self.forward_adj.get(norm_path, set())),
            'direct_dependencies': sorted(list(self.forward_adj.get(norm_path, set()))),
            'direct_referencer_count': len(self.reverse_adj.get(norm_path, set())),
            'direct_referencers': sorted(list(self.reverse_adj.get(norm_path, set()))),
            'transitive_dependencies_count': deps['total_dependencies'],
            'potentially_affected_count': affected['total_potentially_affected'],
            'impact_risk': affected['potential_risk_level'],
        }

    def build_from_session(self, session, root_folder: str = '/Game', asset_limit: int = 100):
        """Discovers assets and queries native get_dependencies and get_referencers."""
        raw_assets = session.invoke('AssetTools', 'find_assets', folder_path=root_folder, name='', recursive=True)
        if not isinstance(raw_assets, list):
            return

        for asset_path in raw_assets[:asset_limit]:
            cls_name = 'Unknown'
            try:
                cls_info = session.invoke('AssetTools', 'get_asset_class', asset_path=asset_path)
                cls_name = str(cls_info)
            except Exception:
                pass

            tags = {}
            try:
                t = session.invoke('AssetTools', 'get_asset_tags', asset_path=asset_path)
                if isinstance(t, dict):
                    tags = {k: v for k, v in t.items() if k in ('ParentClass', 'NativeParentClass', 'ItemTypeDisplayName')}
            except Exception:
                pass

            self.add_node(asset_path, asset_type=cls_name, exists=True, metadata=tags)

            # Query dependencies
            try:
                deps = session.invoke('AssetTools', 'get_dependencies', asset_path=asset_path)
                if isinstance(deps, list):
                    for d in deps:
                        self.add_edge(asset_path, d, edge_type='dependency')
            except Exception as exc:
                logger.debug("Failed get_dependencies for %s: %s", asset_path, exc)

            # Query referencers
            try:
                refs = session.invoke('AssetTools', 'get_referencers', asset_path=asset_path)
                if isinstance(refs, list):
                    for r in refs:
                        self.add_edge(r, asset_path, edge_type='referencer')
            except Exception as exc:
                logger.debug("Failed get_referencers for %s: %s", asset_path, exc)

    def to_dict(self) -> Dict[str, Any]:
        return {
            'nodes': self.nodes,
            'edges': [{'source': s, 'target': t, 'type': self.edge_types.get((s, t), 'reference')}
                      for s, targets in self.forward_adj.items() for t in targets],
            'statistics': {
                'total_nodes': len(self.nodes),
                'total_edges': len(self.edge_types),
                'cycles_detected': len(self.find_cycles()),
                'strongly_connected_components': len(self.find_strongly_connected_components()),
            }
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'AssetDependencyGraph':
        graph = cls()
        for path, n in data.get('nodes', {}).items():
            graph.add_node(path, asset_type=n.get('class'), exists=n.get('exists', True), metadata=n.get('metadata', {}))
        for edge in data.get('edges', []):
            graph.add_edge(edge['source'], edge['target'], edge_type=edge.get('type', 'reference'))
        return graph


def main():
    parser = argparse.ArgumentParser(description='ARC 02 Asset Dependency Graph Engine')
    parser.add_argument('--project', help='Path to .uproject file')
    parser.add_argument('--engine', help='Path to Unreal Engine directory')
    parser.add_argument('--endpoint', default='http://127.0.0.1:8000/mcp')
    parser.add_argument('--asset', help='Inspect dependencies/impact for specific asset')
    parser.add_argument('--depth', type=int, default=3, help='Max traversal depth')
    parser.add_argument('--impact', action='store_true', help='Show blast radius impact analysis')
    parser.add_argument('--cycles', action='store_true', help='Find circular dependencies')
    parser.add_argument('--limit', type=int, default=50, help='Max assets to discover')
    parser.add_argument('--output', default='reports/asset_dependencies.json', help='Output JSON path')
    args = parser.parse_args()

    from unreal_session import UnrealSession
    from pathlib import Path

    project = Path(args.project).resolve() if args.project else None
    engine = Path(args.engine).resolve() if args.engine else None

    session = UnrealSession(endpoint=args.endpoint)
    session.connect(full=False)
    if project and engine:
        session.verify_identity(project, engine)

    graph = AssetDependencyGraph()
    print(f"Scanning assets in /Game (limit={args.limit})...")
    graph.build_from_session(session, root_folder='/Game', asset_limit=args.limit)

    stats = graph.to_dict()['statistics']
    print(f"Graph constructed: {stats['total_nodes']} nodes, {stats['total_edges']} edges.")

    cycles = graph.find_cycles()
    if cycles:
        print(f"WARNING: {len(cycles)} cycles detected:")
        for c in cycles[:3]:
            print("  Cycle:", ' -> '.join(c))
    else:
        print("Cycles detected: 0 (Graph is acyclic)")

    if args.asset:
        print(f"\nDependency summary for {args.asset}:")
        summary = graph.summarize_asset(args.asset, max_depth=args.depth)
        print(json.dumps(summary, indent=2))
        if args.impact:
            print(f"\nImpact / Blast-Radius Analysis:")
            impact = graph.get_affected_assets(args.asset, max_depth=args.depth)
            print(json.dumps(impact, indent=2))

    out_path = Path(args.output)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(graph.to_dict(), indent=2), encoding='utf-8')
    print(f"\nDependency graph saved to: {out_path}")


if __name__ == '__main__':
    main()
