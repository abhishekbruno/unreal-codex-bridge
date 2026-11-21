import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from inspect_project import (
    inspect_project_metadata,
    inspect_toolsets,
    inspect_scene,
    inspect_assets,
    inspect_blueprints,
    run_inspection,
)
from bridge_mcp import MCPError


class TestInspectProject(unittest.TestCase):
    def setUp(self):
        self.session = MagicMock()
        self.session.names = [
            'editor_toolset.toolsets.actor.ActorTools',
            'editor_toolset.toolsets.scene.SceneTools',
            'editor_toolset.toolsets.blueprint.BlueprintTools',
        ]
        self.session.catalog = [
            {
                'name': 'editor_toolset.toolsets.actor.ActorTools',
                'tools': [
                    {'name': 'get_label', 'description': 'Gets actor label'},
                    {'name': 'get_actor_transform', 'description': 'Gets transform'},
                ],
            }
        ]

    def test_inspect_project_metadata(self):
        self.session.verify_identity.return_value = {
            'listener': {'LocalAddress': '127.0.0.1', 'ProcessId': 1234},
            'mcp_log_entries': ['LogInit: Engine Version: 5.8.4'],
        }
        self.session.invoke.return_value = '/Game/Maps/TestMap'

        with patch('inspect_project.check_engine') as mock_check:
            mock_check.return_value = {'MajorVersion': 5, 'MinorVersion': 8, 'PatchVersion': 4, 'Changelist': 58902052}
            meta = inspect_project_metadata(self.session, Path('D:/Project/Game.uproject'), Path('D:/UE_5.8'))

        self.assertEqual(meta['name'], 'Game')
        self.assertEqual(meta['engine_version'], '5.8.4')
        self.assertEqual(meta['active_level'], '/Game/Maps/TestMap')
        self.assertEqual(meta['listener']['LocalAddress'], '127.0.0.1')

    def test_inspect_toolsets(self):
        res = inspect_toolsets(self.session)
        self.assertEqual(res['total_discovered_toolsets'], 3)
        self.assertEqual(res['cataloged_count'], 1)
        self.assertEqual(res['catalog'][0]['short_name'], 'ActorTools')
        self.assertEqual(res['catalog'][0]['tool_count'], 2)

    def test_inspect_scene_bounded_limits_and_structure(self):
        fake_actors = [{'refPath': f'/Game/Map.Map:PersistentLevel.Actor_{i}'} for i in range(10)]
        def mock_invoke(toolset, tool, **kwargs):
            if tool == 'get_current_level':
                return '/Game/Map'
            if tool == 'find_actors':
                return fake_actors
            if tool == 'get_label':
                return 'TestActor'
            if tool == 'get_class':
                return {'refPath': '/Script/Engine.StaticMeshActor'}
            if tool == 'get_actor_transform':
                return {'location': {'x': 0, 'y': 0, 'z': 0}}
            if tool == 'get_components':
                return [{'refPath': 'comp1'}]
            if tool == 'get_tags':
                return ['TestTag']
            return {}

        self.session.invoke.side_effect = mock_invoke
        res = inspect_scene(self.session, actor_limit=3)

        self.assertEqual(res['total_actors_found'], 10)
        self.assertEqual(res['actors_inspected_count'], 3)
        self.assertEqual(len(res['actors']), 3)
        self.assertEqual(res['class_distribution'].get('StaticMeshActor'), 3)
        self.assertEqual(res['actors'][0]['label'], 'TestActor')
        self.assertEqual(res['actors'][0]['component_count'], 1)

    def test_inspect_scene_resilient_to_property_errors(self):
        fake_actors = [{'refPath': '/Game/Map:Actor1'}]
        def mock_invoke(toolset, tool, **kwargs):
            if tool == 'find_actors':
                return fake_actors
            if tool == 'get_label':
                raise RuntimeError('Simulated COM error')
            if tool == 'get_class':
                return {'refPath': '/Script/Engine.Actor'}
            return {}

        self.session.invoke.side_effect = mock_invoke
        res = inspect_scene(self.session, actor_limit=5)
        self.assertEqual(len(res['actors']), 1)
        self.assertIn('label_error', res['actors'][0])
        self.assertIn('Simulated COM error', res['actors'][0]['label_error'])

    def test_inspect_assets_bounded_limits(self):
        fake_assets = [f'/Game/Asset_{i}' for i in range(25)]
        def mock_invoke(toolset, tool, **kwargs):
            if tool == 'find_assets':
                return fake_assets
            if tool == 'get_asset_class':
                return 'StaticMesh'
            if tool == 'get_asset_tags':
                return {'ItemTypeDisplayName': 'Static Mesh'}
            return {}

        self.session.invoke.side_effect = mock_invoke
        res = inspect_assets(self.session, root_folder='/Game', asset_limit=5)

        self.assertEqual(res['total_assets_found'], 25)
        self.assertEqual(res['assets_inspected_count'], 5)
        self.assertEqual(res['class_distribution'].get('StaticMesh'), 5)
        self.assertEqual(res['asset_sample'][0]['tags_summary']['ItemTypeDisplayName'], 'Static Mesh')

    def test_inspect_blueprints(self):
        self.session.load_toolset.return_value = {
            'name': 'editor_toolset.toolsets.blueprint.BlueprintTools',
            'tools': [{'name': 'get_graph_dsl_docs', 'description': 'DSL docs'}]
        }
        def mock_invoke(toolset, tool, **kwargs):
            if tool == 'get_graph_dsl_docs':
                return 'GRAMMAR OVERVIEW\n(event ...)'
            if tool == 'list_graphs':
                return [{'refPath': 'EventGraph'}]
            if tool == 'list_variables':
                return [{'name': 'Health', 'type': 'float'}]
            if tool == 'list_functions':
                return ['CustomFunc']
            return {}

        self.session.invoke.side_effect = mock_invoke

        sample_assets = [
            {'path': '/Game/BP_Player', 'name': 'BP_Player', 'class': 'BP_Player_C', 'tags_summary': {'ParentClass': 'Character'}},
            {'path': '/Game/M_Floor', 'name': 'M_Floor', 'class': 'Material', 'tags_summary': {}},
        ]
        res = inspect_blueprints(self.session, sample_assets, blueprint_limit=10)

        self.assertTrue(res['graph_dsl_available'])
        self.assertEqual(res['blueprints_found_in_sample'], 1)
        self.assertEqual(res['blueprints_inspected_count'], 1)
        self.assertEqual(res['blueprints'][0]['name'], 'BP_Player')
        self.assertEqual(res['blueprints'][0]['graphs'], ['EventGraph'])

    def test_read_only_safety_guarantee(self):
        # Verify no write tools were ever requested or invoked in inspect_scene, inspect_assets, inspect_blueprints
        forbidden_tools = {'set_properties', 'set_actor_transform', 'write_file', 'save_assets',
                           'write_graph_dsl', 'remove_from_scene', 'add_to_scene_from_asset'}
        invoked_tools = set()

        def tracking_invoke(toolset, tool, **kwargs):
            invoked_tools.add(tool)
            if tool == 'find_actors': return []
            if tool == 'find_assets': return []
            if tool == 'get_graph_dsl_docs': return 'GRAMMAR'
            return {}

        self.session.invoke.side_effect = tracking_invoke
        self.session.load_toolset.return_value = {'name': 'BlueprintTools', 'tools': []}

        inspect_scene(self.session)
        inspect_assets(self.session)
        inspect_blueprints(self.session, [])

        self.assertTrue(invoked_tools.isdisjoint(forbidden_tools), f"Forbidden tools invoked: {invoked_tools & forbidden_tools}")


if __name__ == '__main__':
    unittest.main()

