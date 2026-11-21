import json
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from project_dependencies import AssetDependencyGraph


class TestAssetDependencyGraph(unittest.TestCase):
    def setUp(self):
        self.graph = AssetDependencyGraph()

    def test_node_categorization_and_metadata(self):
        self.graph.add_node('/Game/BP_Player', asset_type='Blueprint')
        self.graph.add_node('/Script/Engine', asset_type='NativePackage')
        self.graph.add_node('/Engine/BasicShapes/Cube', asset_type='StaticMesh')

        nodes = self.graph.nodes
        self.assertEqual(nodes['/Game/BP_Player']['category'], 'game_asset')
        self.assertEqual(nodes['/Script/Engine']['category'], 'native_script')
        self.assertEqual(nodes['/Engine/BasicShapes/Cube']['category'], 'engine_asset')

    def test_direct_dependencies_and_referencers(self):
        self.graph.add_edge('/Game/BP_Player', '/Game/M_PlayerMat')
        self.graph.add_edge('/Game/BP_Player', '/Script/Engine')
        self.graph.add_edge('/Game/BP_Weapon', '/Game/BP_Player')

        # Direct dependencies of BP_Player
        deps = self.graph.get_direct_dependencies('/Game/BP_Player')
        self.assertEqual(deps, ['/Game/M_PlayerMat', '/Script/Engine'])

        # Direct referencers of BP_Player
        refs = self.graph.get_direct_referencers('/Game/BP_Player')
        self.assertEqual(refs, ['/Game/BP_Weapon'])

    def test_transitive_dependencies_with_depth_bounding(self):
        # Chain: A -> B -> C -> D -> E
        self.graph.add_edge('/Game/A', '/Game/B')
        self.graph.add_edge('/Game/B', '/Game/C')
        self.graph.add_edge('/Game/C', '/Game/D')
        self.graph.add_edge('/Game/D', '/Game/E')

        # Depth 1: should only see B
        d1 = self.graph.get_transitive_dependencies('/Game/A', max_depth=1)
        self.assertEqual(d1['total_dependencies'], 1)
        self.assertEqual(d1['all_dependencies'], ['/Game/B'])

        # Depth 2: should see B, C
        d2 = self.graph.get_transitive_dependencies('/Game/A', max_depth=2)
        self.assertEqual(d2['total_dependencies'], 2)
        self.assertEqual(d2['all_dependencies'], ['/Game/B', '/Game/C'])

        # Depth 4: should see B, C, D, E
        d4 = self.graph.get_transitive_dependencies('/Game/A', max_depth=4)
        self.assertEqual(d4['total_dependencies'], 4)
        self.assertEqual(d4['all_dependencies'], ['/Game/B', '/Game/C', '/Game/D', '/Game/E'])

    def test_blast_radius_impact_analysis(self):
        # Tree: Core -> Sub1, Core -> Sub2, Sub1 -> Leaf1
        # Reverse: Leaf1 depends on Sub1; Sub1 and Sub2 depend on Core
        self.graph.add_edge('/Game/Leaf1', '/Game/Sub1')
        self.graph.add_edge('/Game/Sub1', '/Game/Core')
        self.graph.add_edge('/Game/Sub2', '/Game/Core')

        # If Core is modified, who is affected?
        impact = self.graph.get_affected_assets('/Game/Core', max_depth=3)
        self.assertEqual(impact['total_potentially_affected'], 3)
        self.assertEqual(sorted(impact['immediate_referencers']), ['/Game/Sub1', '/Game/Sub2'])
        self.assertEqual(impact['transitive_referencers'], ['/Game/Leaf1'])
        self.assertIn('potential_risk_level', impact)

    def test_cycle_detection(self):
        # A -> B -> C -> A (cycle)
        self.graph.add_edge('/Game/A', '/Game/B')
        self.graph.add_edge('/Game/B', '/Game/C')
        self.graph.add_edge('/Game/C', '/Game/A')
        # Independent node
        self.graph.add_edge('/Game/A', '/Game/D')

        cycles = self.graph.find_cycles()
        self.assertGreaterEqual(len(cycles), 1)
        # Verify cycle contains A, B, C
        cycle_nodes = set(cycles[0])
        self.assertTrue({'/Game/A', '/Game/B', '/Game/C'}.issubset(cycle_nodes))

    def test_strongly_connected_components(self):
        # Component 1: A <-> B
        self.graph.add_edge('/Game/A', '/Game/B')
        self.graph.add_edge('/Game/B', '/Game/A')
        # Independent linear chain: C -> D
        self.graph.add_edge('/Game/C', '/Game/D')

        sccs = self.graph.find_strongly_connected_components()
        self.assertEqual(len(sccs), 1)
        self.assertEqual(sccs[0], ['/Game/A', '/Game/B'])

    def test_unresolved_references(self):
        self.graph.add_node('/Game/ValidAsset', exists=True)
        self.graph.add_node('/Game/MissingAsset', exists=False)
        self.graph.add_edge('/Game/ValidAsset', '/Game/MissingAsset')

        missing = self.graph.find_unresolved_references()
        self.assertEqual(len(missing), 1)
        self.assertEqual(missing[0]['referencer'], '/Game/ValidAsset')
        self.assertEqual(missing[0]['missing_target'], '/Game/MissingAsset')

    def test_serialization_roundtrip(self):
        self.graph.add_node('/Game/A', asset_type='Blueprint')
        self.graph.add_node('/Game/B', asset_type='Material')
        self.graph.add_edge('/Game/A', '/Game/B', edge_type='material_ref')

        data = self.graph.to_dict()
        restored = AssetDependencyGraph.from_dict(data)

        self.assertEqual(len(restored.nodes), 2)
        self.assertEqual(restored.get_direct_dependencies('/Game/A'), ['/Game/B'])
        self.assertEqual(restored.get_direct_referencers('/Game/B'), ['/Game/A'])


if __name__ == '__main__':
    unittest.main()

