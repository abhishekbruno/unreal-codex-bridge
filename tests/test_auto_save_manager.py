"""Unit tests for the centralized AutoSaveManager and entity auto-save system."""

import json
import os
from pathlib import Path
import sys
import unittest
from unittest.mock import MagicMock, call

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))

from auto_save_manager import (
    AutoSaveManager,
    CreationTransaction,
    extract_package_path,
    is_entity_creation_tool,
    is_graph_construction_tool,
    get_entity_type_for_tool,
)
from bridge_mcp import MCPError
from editor_state_guard import EditorStateGuard


class MockUnrealSession:
    """Mock session simulating Unreal MCP tools and package state."""

    def __init__(self, current_level='/Game/Maps/TestLevel', auto_save=True):
        self.current_level = current_level
        self.auto_save_enabled = auto_save
        self._auto_save_manager = None
        self.pie_running = False
        self.fail_save = False
        self.packages_dirty = {}
        self.packages_exist = {current_level: True}
        self.saved_packages = []
        self.saved_actors = []
        self.calls = []

    @property
    def auto_save_manager(self):
        if self._auto_save_manager is None:
            self._auto_save_manager = AutoSaveManager(self, enabled=self.auto_save_enabled)
        return self._auto_save_manager

    @auto_save_manager.setter
    def auto_save_manager(self, manager):
        self._auto_save_manager = manager

    def verify_identity(self, project, engine):
        return {'verified': True, 'project': str(project), 'engine': str(engine)}

    def invoke(self, toolset, tool_name, **arguments):
        short_ts = toolset.split('.')[-1]
        short_tool = tool_name.split('.')[-1]
        self.calls.append((short_ts, short_tool, arguments))

        # Check PIE
        if short_ts == 'EditorAppToolset' and short_tool == 'IsPIERunning':
            return self.pie_running

        # SceneTools
        if short_ts == 'SceneTools':
            if short_tool == 'get_current_level':
                return self.current_level
            if short_tool == 'load_level':
                self.current_level = arguments['level_path']
                return True
            if short_tool == 'save_actor':
                self.saved_actors.append(arguments['actor'])
                return True
            if short_tool == 'add_to_scene_from_asset':
                asset_path = arguments['asset_path']
                name = arguments['name']
                ref = {'refPath': f"{self.current_level}.{self.current_level.split('/')[-1]}:PersistentLevel.{name}"}
                self.packages_dirty[self.current_level] = True
                ret_val = ref
                if getattr(self, 'auto_save_enabled', False):
                    if is_entity_creation_tool(toolset, tool_name):
                        self.auto_save_manager.handle_post_invoke(toolset, tool_name, arguments, ret_val)
                return ret_val
            if short_tool == 'add_to_scene_from_class':
                name = arguments['name']
                ref = {'refPath': f"{self.current_level}.{self.current_level.split('/')[-1]}:PersistentLevel.{name}"}
                self.packages_dirty[self.current_level] = True
                ret_val = ref
                if getattr(self, 'auto_save_enabled', False):
                    if is_entity_creation_tool(toolset, tool_name):
                        self.auto_save_manager.handle_post_invoke(toolset, tool_name, arguments, ret_val)
                return ret_val
            if short_tool == 'find_actors':
                name = arguments.get('name', '')
                return [{'refPath': f"{self.current_level}.{self.current_level.split('/')[-1]}:PersistentLevel.{name}"}]

        # AssetTools
        if short_ts == 'AssetTools':
            if short_tool == 'is_dirty':
                pkg = arguments['asset_path']
                return self.packages_dirty.get(pkg, False)
            if short_tool == 'exists':
                pkg = arguments.get('path') or arguments.get('asset_path')
                return self.packages_exist.get(pkg, True)
            if short_tool == 'save_assets':
                if self.fail_save:
                    return False
                paths = arguments['asset_paths']
                if not paths:
                    raise MCPError("Cannot call save_assets with empty array")
                for p in paths:
                    self.saved_packages.append(p)
                    self.packages_dirty[p] = False
                    self.packages_exist[p] = True
                return True
            if short_tool == 'load_asset':
                pkg = arguments['asset_path']
                return {'refPath': f"{pkg}.{pkg.split('/')[-1]}"}
            if short_tool == 'duplicate':
                dest = arguments.get('new_path') or arguments.get('destination_path')
                self.packages_dirty[dest] = True
                self.packages_exist[dest] = True
                ret_val = True
                if getattr(self, 'auto_save_enabled', False):
                    if is_entity_creation_tool(toolset, tool_name):
                        self.auto_save_manager.handle_post_invoke(toolset, tool_name, arguments, ret_val)
                return ret_val

        # BlueprintTools
        if short_ts == 'BlueprintTools':
            if short_tool == 'create':
                pkg = f"{arguments['folder_path'].rstrip('/')}/{arguments['asset_name']}"
                self.packages_dirty[pkg] = True
                self.packages_exist[pkg] = True
                ret_val = {'refPath': f"{pkg}.{arguments['asset_name']}"}
                if getattr(self, 'auto_save_enabled', False):
                    if is_entity_creation_tool(toolset, tool_name):
                        self.auto_save_manager.handle_post_invoke(toolset, tool_name, arguments, ret_val)
                return ret_val
            if short_tool == 'get_default_object':
                bp_ref = arguments['blueprint']
                p = extract_package_path(bp_ref)
                name = p.split('/')[-1]
                return {'refPath': f"{p}.Default__{name}_C"}
            if short_tool in ('create_node', 'delete_node', 'connect_pins', 'break_pins',
                              'write_graph_dsl', 'set_node_position', 'add_variable', 'compile_blueprint'):
                return True

        # MaterialTools
        if short_ts == 'MaterialTools':
            if short_tool in ('create_material', 'create_function', 'create_parameter_collection'):
                pkg = f"{arguments['folder_path'].rstrip('/')}/{arguments['asset_name']}"
                self.packages_dirty[pkg] = True
                self.packages_exist[pkg] = True
                ret_val = {'refPath': f"{pkg}.{arguments['asset_name']}"}
                if getattr(self, 'auto_save_enabled', False):
                    if is_entity_creation_tool(toolset, tool_name):
                        self.auto_save_manager.handle_post_invoke(toolset, tool_name, arguments, ret_val)
                return ret_val

        # MaterialInstanceTools
        if short_ts == 'MaterialInstanceTools':
            if short_tool == 'create':
                pkg = f"{arguments['folder_path'].rstrip('/')}/{arguments['asset_name']}"
                self.packages_dirty[pkg] = True
                self.packages_exist[pkg] = True
                ret_val = {'refPath': f"{pkg}.{arguments['asset_name']}"}
                if getattr(self, 'auto_save_enabled', False):
                    if is_entity_creation_tool(toolset, tool_name):
                        self.auto_save_manager.handle_post_invoke(toolset, tool_name, arguments, ret_val)
                return ret_val

        # ActorTools
        if short_ts == 'ActorTools':
            if short_tool == 'add_component':
                comp_name = arguments['name']
                owner = arguments['owner']
                owner_pkg = extract_package_path(owner)
                self.packages_dirty[owner_pkg] = True
                ret_val = {'refPath': f"{owner_pkg}:PersistentLevel.{comp_name}"}
                if getattr(self, 'auto_save_enabled', False):
                    if is_entity_creation_tool(toolset, tool_name):
                        self.auto_save_manager.handle_post_invoke(toolset, tool_name, arguments, ret_val)
                return ret_val
            if short_tool == 'get_actor_transform':
                return {'location': {'x': 0, 'y': 0, 'z': 0}}
            if short_tool == 'get_label':
                return 'TestLabel'
            if short_tool == 'get_components':
                return [{'refPath': '/Game/Test.BP_Test:Comp_GEN'}]
            if short_tool == 'get_component_actor':
                return {'refPath': f"{self.current_level}.{self.current_level.split('/')[-1]}:PersistentLevel.Actor1"}

        # ObjectTools
        if short_ts == 'ObjectTools':
            if short_tool == 'set_properties':
                return True
            if short_tool == 'get_properties':
                return json.dumps({})
            if short_tool == 'get_class':
                return {'refPath': '/Script/Engine.Material'}

        return True


class TestPackageExtraction(unittest.TestCase):
    """Test package normalization and path validation."""

    def test_clean_package_path(self):
        self.assertEqual(extract_package_path('/Game/Blueprints/BP_Player'), '/Game/Blueprints/BP_Player')

    def test_asset_reference_with_dot(self):
        self.assertEqual(extract_package_path('/Game/Blueprints/BP_Player.BP_Player'), '/Game/Blueprints/BP_Player')

    def test_actor_subobject_reference(self):
        self.assertEqual(
            extract_package_path('/Game/Maps/MainMap.MainMap:PersistentLevel.Warrior_1'),
            '/Game/Maps/MainMap'
        )

    def test_cdo_subobject_reference(self):
        self.assertEqual(
            extract_package_path('/Game/Blueprints/BP_Player.Default__BP_Player_C'),
            '/Game/Blueprints/BP_Player'
        )

    def test_external_actor_ofpa(self):
        ref = '/Game/Maps/World/__ExternalActors__/World/A/B/ActorUUID.ActorUUID'
        self.assertEqual(
            extract_package_path(ref),
            '/Game/Maps/World/__ExternalActors__/World/A/B/ActorUUID'
        )

    def test_dict_reference(self):
        self.assertEqual(
            extract_package_path({'refPath': '/Game/Materials/M_Base.M_Base'}),
            '/Game/Materials/M_Base'
        )
        self.assertEqual(
            extract_package_path({'new_path': '/Game/Meshes/SM_Box'}),
            '/Game/Meshes/SM_Box'
        )

    def test_reject_engine_package(self):
        with self.assertRaises(ValueError):
            extract_package_path('/Engine/BasicShapes/Cube')

    def test_reject_directory_traversal(self):
        with self.assertRaises(ValueError):
            extract_package_path('/Game/Maps/../Secret')

    def test_reject_non_game_package(self):
        with self.assertRaises(ValueError):
            extract_package_path('/Temp/Untitled_1')


class TestToolCategorization(unittest.TestCase):
    """Test entity creation and graph construction tool recognition."""

    def test_entity_creation_tools(self):
        self.assertTrue(is_entity_creation_tool('SceneTools', 'add_to_scene_from_asset'))
        self.assertTrue(is_entity_creation_tool('SceneTools', 'add_to_scene_from_class'))
        self.assertTrue(is_entity_creation_tool('BlueprintTools', 'create'))
        self.assertTrue(is_entity_creation_tool('MaterialTools', 'create_material'))
        self.assertTrue(is_entity_creation_tool('MaterialInstanceTools', 'create'))
        self.assertTrue(is_entity_creation_tool('ActorTools', 'add_component'))
        self.assertTrue(is_entity_creation_tool('AssetTools', 'duplicate'))

    def test_graph_construction_tools(self):
        self.assertTrue(is_graph_construction_tool('BlueprintTools', 'create_node'))
        self.assertTrue(is_graph_construction_tool('BlueprintTools', 'connect_pins'))
        self.assertTrue(is_graph_construction_tool('BlueprintTools', 'write_graph_dsl'))
        self.assertTrue(is_graph_construction_tool('BlueprintTools', 'set_node_position'))
        self.assertFalse(is_entity_creation_tool('BlueprintTools', 'create_node'))
        self.assertFalse(is_entity_creation_tool('BlueprintTools', 'write_graph_dsl'))


class TestEntityAutoSave(unittest.TestCase):
    """Test automatic saving of owning packages for all supported entity types."""

    def setUp(self):
        self.session = MockUnrealSession()
        self.manager = self.session.auto_save_manager

    def test_actor_creation_auto_saves_owning_level(self):
        actor_ref = self.session.invoke(
            'SceneTools', 'add_to_scene_from_asset',
            asset_path='/Engine/BasicShapes/Cube', name='AutoCube',
            xform={'location': {'x': 0, 'y': 0, 'z': 100}}
        )
        self.assertIn('/Game/Maps/TestLevel', self.session.saved_packages)
        self.assertFalse(self.session.packages_dirty['/Game/Maps/TestLevel'])
        self.assertTrue(any(call[1] == 'get_actor_transform' for call in self.session.calls))

    def test_actor_from_class_auto_saves_level(self):
        actor_ref = self.session.invoke(
            'SceneTools', 'add_to_scene_from_class',
            actor_type={'refPath': '/Script/Engine.PointLight'}, name='MyLight',
            xform={'location': {'x': 0, 'y': 0, 'z': 200}}
        )
        self.assertIn('/Game/Maps/TestLevel', self.session.saved_packages)
        self.assertFalse(self.session.packages_dirty['/Game/Maps/TestLevel'])

    def test_external_actor_ofpa_saves_both_level_and_external_package(self):
        ext_ref = {'refPath': '/Game/Maps/TestLevel/__ExternalActors__/TestLevel/A/B/UUID123.UUID123'}
        res = self.manager.auto_save_entity('actor', entity_ref=ext_ref)
        self.assertIn('/Game/Maps/TestLevel', self.session.saved_packages)
        self.assertIn('/Game/Maps/TestLevel/__ExternalActors__/TestLevel/A/B/UUID123', self.session.saved_packages)

    def test_blueprint_creation_auto_saves_asset_package(self):
        bp = self.session.invoke(
            'BlueprintTools', 'create',
            folder_path='/Game/Blueprints', asset_name='BP_TestActor',
            asset_type={'refPath': '/Script/Engine.Actor'}
        )
        self.assertIn('/Game/Blueprints/BP_TestActor', self.session.saved_packages)
        self.assertFalse(self.session.packages_dirty['/Game/Blueprints/BP_TestActor'])
        # Verify persistence called load_asset
        self.assertTrue(any(call[1] == 'load_asset' and call[2]['asset_path'] == '/Game/Blueprints/BP_TestActor'
                            for call in self.session.calls))

    def test_material_creation_auto_saves_asset_package(self):
        mat = self.session.invoke(
            'MaterialTools', 'create_material',
            folder_path='/Game/Materials', asset_name='M_Metal'
        )
        self.assertIn('/Game/Materials/M_Metal', self.session.saved_packages)
        self.assertFalse(self.session.packages_dirty['/Game/Materials/M_Metal'])

    def test_material_instance_auto_saves_asset_package(self):
        mi = self.session.invoke(
            'MaterialInstanceTools', 'create',
            folder_path='/Game/Materials', asset_name='MI_Metal_Rough',
            parent={'refPath': '/Game/Materials/M_Metal.M_Metal'}
        )
        self.assertIn('/Game/Materials/MI_Metal_Rough', self.session.saved_packages)
        self.assertFalse(self.session.packages_dirty['/Game/Materials/MI_Metal_Rough'])

    def test_component_on_actor_auto_saves_actor_level(self):
        actor_ref = {'refPath': '/Game/Maps/TestLevel.TestLevel:PersistentLevel.MyActor'}
        comp = self.session.invoke(
            'ActorTools', 'add_component',
            owner=actor_ref,
            component_type={'refPath': '/Script/Engine.StaticMeshComponent'},
            name='Mesh1'
        )
        self.assertIn('/Game/Maps/TestLevel', self.session.saved_packages)
        self.assertFalse(self.session.packages_dirty['/Game/Maps/TestLevel'])

    def test_component_on_blueprint_auto_saves_blueprint_package(self):
        bp_ref = {'refPath': '/Game/Blueprints/BP_Warrior.Default__BP_Warrior_C'}
        comp = self.session.invoke(
            'ActorTools', 'add_component',
            owner=bp_ref,
            component_type={'refPath': '/Script/Engine.BoxComponent'},
            name='TriggerBox'
        )
        self.assertIn('/Game/Blueprints/BP_Warrior', self.session.saved_packages)
        self.assertFalse(self.session.packages_dirty['/Game/Blueprints/BP_Warrior'])

    def test_asset_duplicate_auto_saves_destination(self):
        self.session.invoke(
            'AssetTools', 'duplicate',
            path='/Game/Maps/TestLevel', new_path='/Game/Maps/ClonedLevel'
        )
        self.assertIn('/Game/Maps/ClonedLevel', self.session.saved_packages)
        self.assertFalse(self.session.packages_dirty['/Game/Maps/ClonedLevel'])


class TestMultiStepCreationTransactions(unittest.TestCase):
    """Test transactions, checkpoints, and uninterrupted graph construction."""

    def setUp(self):
        self.session = MockUnrealSession()
        self.manager = self.session.auto_save_manager

    def test_graph_construction_does_not_interrupt_with_premature_saves(self):
        bp_pkg = '/Game/Blueprints/BP_Complex'
        with self.manager.transaction(name='build_bp', entity_type='blueprint', package_path=bp_pkg) as tx:
            bp = self.session.invoke(
                'BlueprintTools', 'create',
                folder_path='/Game/Blueprints', asset_name='BP_Complex',
                asset_type={'refPath': '/Script/Engine.Actor'}
            )
            # Standalone auto-save should NOT have run yet because transaction is active
            self.assertEqual(self.session.saved_packages, [])

            # Step 1: Add components & save checkpoint
            self.session.invoke(
                'ActorTools', 'add_component',
                owner=bp, component_type={'refPath': '/Script/Engine.StaticMeshComponent'}, name='Mesh'
            )
            tx.checkpoint('components_added')
            self.assertEqual(self.session.saved_packages, [bp_pkg])
            self.assertEqual(len(tx.checkpoints), 1)

            # Step 2: Add variables & save checkpoint
            self.session.invoke('BlueprintTools', 'add_variable', blueprint=bp, name='Health', type_name='float')
            tx.checkpoint('variables_added')
            self.assertEqual(self.session.saved_packages, [bp_pkg, bp_pkg])
            self.assertEqual(len(tx.checkpoints), 2)

            # Step 3: Graph construction (multiple nodes, connections)
            # None of these should trigger any saves!
            save_count_before_graph = len(self.session.saved_packages)
            for i in range(5):
                self.session.invoke('BlueprintTools', 'create_node')
                self.session.invoke('BlueprintTools', 'connect_pins')
                self.session.invoke('BlueprintTools', 'set_node_position')
            self.session.invoke('BlueprintTools', 'write_graph_dsl')

            # Uninterrupted graph construction verified: no saves occurred!
            self.assertEqual(len(self.session.saved_packages), save_count_before_graph)

            # Step 4: Compile
            self.session.invoke('BlueprintTools', 'compile_blueprint', blueprint=bp)

        # On exit, transaction committed final state:
        self.assertEqual(tx.status, 'COMMITTED')
        self.assertGreater(len(self.session.saved_packages), save_count_before_graph)
        self.assertFalse(self.session.packages_dirty[bp_pkg])

    def test_failed_transaction_aborts_without_saving_final_corrupted_state(self):
        bp_pkg = '/Game/Blueprints/BP_Broken'
        try:
            with self.manager.transaction(name='broken_bp', entity_type='blueprint', package_path=bp_pkg) as tx:
                self.session.invoke(
                    'BlueprintTools', 'create',
                    folder_path='/Game/Blueprints', asset_name='BP_Broken',
                    asset_type={'refPath': '/Script/Engine.Actor'}
                )
                raise RuntimeError("Compiler explosion")
        except RuntimeError:
            pass

        self.assertEqual(tx.status, 'ABORTED')
        self.assertFalse(tx.committed)

    def test_transaction_validate_fn_rejection(self):
        bp_pkg = '/Game/Blueprints/BP_Invalid'
        with self.assertRaisesRegex(MCPError, 'Validation failed'):
            with self.manager.transaction(name='invalid_bp', entity_type='blueprint',
                                          package_path=bp_pkg, validate_fn=lambda: False) as tx:
                pass


class TestEdgeCasesAndDisabledMode(unittest.TestCase):
    """Test edge cases, persistence failure detection, and disabled mode."""

    def setUp(self):
        self.session = MockUnrealSession()
        self.manager = self.session.auto_save_manager

    def test_disabled_auto_save(self):
        self.session.auto_save_enabled = False
        self.manager.enabled = False
        self.session.invoke(
            'SceneTools', 'add_to_scene_from_asset',
            asset_path='/Engine/BasicShapes/Cube', name='ManualCube',
            xform={'location': {'x': 0, 'y': 0, 'z': 0}}
        )
        self.assertEqual(self.session.saved_packages, [])
        self.assertTrue(self.session.packages_dirty.get('/Game/Maps/TestLevel', False))

    def test_component_owner_resolved_via_get_component_actor(self):
        # Component created without explicit owner_ref
        comp_ref = {'refPath': '/Game/Maps/TestLevel:PersistentLevel.SpecialComponent'}
        res = self.manager.auto_save_entity('component', entity_ref=comp_ref)
        self.assertIn('/Game/Maps/TestLevel', self.session.saved_packages)
        self.assertFalse(self.session.packages_dirty['/Game/Maps/TestLevel'])

    def test_persistence_fails_if_package_remains_dirty(self):
        pkg = '/Game/Maps/DirtyMap'
        self.session.packages_dirty[pkg] = True
        with self.assertRaisesRegex(MCPError, 'package /Game/Maps/DirtyMap is dirty'):
            self.manager.verify_persistence('asset', package_path=pkg)

    def test_persistence_fails_if_asset_does_not_exist(self):
        pkg = '/Game/Maps/GhostMap'
        self.session.packages_exist[pkg] = False
        with self.assertRaisesRegex(MCPError, 'package /Game/Maps/GhostMap does not exist'):
            self.manager.verify_persistence('asset', package_path=pkg)

    def test_disk_file_verification(self):
        import tempfile
        with tempfile.TemporaryDirectory() as td:
            proj = Path(td) / 'TestProject.uproject'
            proj.write_text('{}')
            content_dir = Path(td) / 'Content' / 'Blueprints'
            content_dir.mkdir(parents=True)
            uasset = content_dir / 'BP_DiskTest.uasset'
            uasset.write_bytes(b'dummy_uasset_content')

            manager_with_project = AutoSaveManager(self.session, project=proj)
            v = manager_with_project.verify_persistence(
                'blueprint', package_path='/Game/Blueprints/BP_DiskTest'
            )
            self.assertTrue(v['verified'])
            disk_checks = [c for c in v['checks'] if c['check'] == 'disk_file_exists']
            self.assertEqual(len(disk_checks), 1)
            self.assertEqual(disk_checks[0]['size'], len(b'dummy_uasset_content'))

    def test_level_transaction_has_auto_saver(self):
        import tempfile
        from level_transaction import LevelTransaction
        with tempfile.TemporaryDirectory() as td:
            tx = LevelTransaction(
                self.session,
                project='/path/Game.uproject',
                engine='/path/UE',
                target='/Game/Maps/TestLevel',
                journal=Path(td) / 'j.json',
                owned=['/Game/Maps/TestLevel'],
                complete_world_state_verified=True
            )
            self.assertIsNotNone(tx.auto_saver)
            self.assertIsInstance(tx.auto_saver, AutoSaveManager)


class TestSafeguardsAndGuardReuse(unittest.TestCase):
    """Test PIE protection, dirty-state verification, and EditorStateGuard reuse."""

    def setUp(self):
        self.session = MockUnrealSession()

    def test_pie_running_blocks_save(self):
        self.session.pie_running = True
        manager = AutoSaveManager(self.session)
        with self.assertRaisesRegex(MCPError, 'PIE running'):
            manager.save_package('/Game/Maps/TestLevel')

    def test_save_failure_raises_mcperror(self):
        self.session.fail_save = True
        manager = AutoSaveManager(self.session)
        with self.assertRaisesRegex(MCPError, 'Save failed'):
            manager.save_package('/Game/Maps/TestLevel')

    def test_guard_authorize_and_save_reuse(self):
        guard = EditorStateGuard(
            self.session,
            project='/fake/MyProject.uproject',
            engine='/fake/UE',
            owned=['/Game/Maps/TestLevel']
        )
        manager = AutoSaveManager(self.session, guard=guard)
        # New package dynamically authorized and saved through EditorStateGuard
        new_pkg = '/Game/Blueprints/BP_DynamicallyAuthorized'
        self.session.packages_dirty[new_pkg] = True
        self.session.packages_exist[new_pkg] = True
        manager.save_package(new_pkg)
        self.assertIn(new_pkg, guard.owned)
        self.assertIn(new_pkg, self.session.saved_packages)


if __name__ == '__main__':
    unittest.main()
